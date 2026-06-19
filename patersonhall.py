from pathlib import Path
import copy
import json
import sys

import numpy as np
import open3d as o3d
from PIL import Image
from geomapi.utils import geometryutils as gmu


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

SHOW_RAYS = False
SHOW_WINDOWS_DOORS = False
WRITE_CITYJSON = True


from lod3_modeler import building_parser as bp
from lod3_modeler import detection_parser as dp
from lod3_modeler import enrichment as fe
from lod3_modeler import image_parser as ip


with (PROJECT_ROOT / "config" / "building_enrichment.json").open("r", encoding="utf-8") as f:
    config = json.load(f)

p = lambda key: PROJECT_ROOT / config[key]


def load_building():
    with p("cityjson").open("r", encoding="utf-8") as f:
        city_json = json.load(f)

    building = bp.parse_cityjson(city_json)
    building["mesh"].translate(config["building_translation"])

    print(f"Building: {building['id']} ({building['name']})")
    print(f"LoD: {building['lod']}")
    print(f"Mesh parts: {len(building['parts'])}")
    return city_json, building


def load_image_nodes():
    image_nodes = ip.image_nodes_from_cams_csv(
        p("cams_csv"),
        image_folder=p("image_dir"),
        depth=config["image_node_depth"],
        focal_length_scale=config["focal_length_scale"],
        transpose_rotation=config["transpose_rotation"],
        transform_translation=config["image_node_translation"],
    )
    selected_node = image_nodes[config["image_node_index"]]
    print(f"ImageNodes: {len(image_nodes)}")
    print(f"Selected node: {config['image_node_index']} - {selected_node.name}")
    return image_nodes, selected_node


def load_selected_image(selected_node):
    image_resource = selected_node.load_resource()
    return Image.fromarray(np.asarray(image_resource)).convert("RGB")


def detect_selected_image(image, model, processor, device):
    boxes, labels, scores = dp.detect_boxes_labels(
        image,
        model,
        processor,
        device,
        config["detection_text"],
        config["box_threshold"],
        config["text_threshold"],
    )
    print(f"Selected image detections: {len(boxes)}")
    return boxes, labels, scores


def debug_selected_rays(building, selected_node, boxes):
    test_pixels = np.array([
        [0, 0],
        [selected_node.imageWidth / 2, selected_node.imageHeight / 2],
        [selected_node.imageWidth, selected_node.imageHeight],
    ])
    test_image_coordinates = np.column_stack((
        test_pixels[:, 0] - selected_node.imageWidth / 2,
        selected_node.imageHeight / 2 - test_pixels[:, 1],
        test_pixels[:, 1] - selected_node.imageHeight / 2,
    ))
    print("Raster to image/camera coordinates [u v x_image y_image_up y_camera_down]:")
    print(np.c_[test_pixels, test_image_coordinates])

    image_points = np.array([
        [0, 0],
        [selected_node.imageWidth, 0],
        [0, selected_node.imageHeight],
        [selected_node.imageWidth, selected_node.imageHeight],
    ])
    image_corner_rays = ip.rays_from_raster_points(selected_node, image_points)

    detection_corners = [ip.box_corners(box) for box in boxes]
    detection_corner_points = np.vstack(detection_corners) if len(detection_corners) else np.empty((0, 2))
    detection_rays = (
        ip.rays_from_raster_points(selected_node, detection_corner_points)
        if len(detection_corner_points)
        else np.empty((0, 6))
    )

    if len(detection_corner_points):
        detection_plane_points = ip.world_points_from_raster_points(
            selected_node,
            detection_corner_points,
            selected_node.depth,
        )
        reprojected = ip.raster_points_from_world_points(selected_node, detection_plane_points)
        errors = np.linalg.norm(reprojected - detection_corner_points, axis=1)
        print(f"BBox corner reprojection max error: {errors.max()}")
        print(np.c_[detection_corner_points[:4], reprojected[:4]])
    else:
        detection_plane_points = np.empty((0, 3))

    corner_distances = np.linalg.norm(
        np.asarray(selected_node.convexHull.vertices)[1:] - selected_node.cartesianTransform[:3, 3],
        axis=1,
    )
    corner_lineset = gmu.rays_to_lineset(image_corner_rays, distances=corner_distances)
    corner_lineset.paint_uniform_color([0, 1, 0])
    hull_lineset = o3d.geometry.LineSet.create_from_triangle_mesh(selected_node.convexHull)
    hull_lineset.paint_uniform_color([0, 0, 1])

    geometries = [building["mesh"], hull_lineset, corner_lineset]
    if len(detection_rays):
        detection_distances = np.linalg.norm(
            detection_plane_points - selected_node.cartesianTransform[:3, 3],
            axis=1,
        )
        detection_lineset = gmu.rays_to_lineset(detection_rays, distances=detection_distances)
        detection_lineset.paint_uniform_color([1, 0, 0])
        geometries.append(detection_lineset)

        line_points = np.asarray(detection_lineset.points)
        line_ends = line_points[np.asarray(detection_lineset.lines)[:, 1]]
        endpoint_errors = np.linalg.norm(line_ends - detection_plane_points, axis=1)
        print(f"Detection lineset image-plane endpoint max error: {endpoint_errors.max()}")

        hits = fe.raycast_rays(building["mesh"], detection_rays)
        hit_mask = np.isfinite(hits).all(axis=1)
        print(f"Detection ray hits: {hit_mask.sum()} / {len(detection_rays)}")

        if hit_mask.any():
            hit_pixels = ip.raster_points_from_world_points(selected_node, hits[hit_mask])
            hit_errors = np.linalg.norm(hit_pixels - detection_corner_points[hit_mask], axis=1)
            print(f"Hit reprojection max error: {hit_errors.max()}")
            print(np.c_[detection_corner_points[hit_mask][:4], hit_pixels[:4]])

    if SHOW_RAYS:
        o3d.visualization.draw_geometries(geometries)


def selected_window_rays(selected_node, boxes, labels, scores):
    rays_per_object = []
    window_labels = []
    window_scores = []

    for box, label, score in zip(boxes, labels, scores):
        if "window" not in str(label).lower():
            continue

        corners = ip.box_corners(box)
        rays = ip.rays_from_raster_points(selected_node, corners)
        rays_per_object.append([
            {"2d_point": tuple(point), "ray": ray}
            for point, ray in zip(corners, rays)
        ])
        window_labels.append(label)
        window_scores.append(float(score))

    rays = {
        Path(selected_node.name).stem: [{
            "rays_per_object": rays_per_object,
            "labels": window_labels,
            "scores": window_scores,
        }]
    }
    print(f"Selected image windows: {len(window_labels)}")
    return rays


def selected_window_door_rays(selected_node, boxes, labels, scores):
    rays_per_object = []
    kept_labels = []
    kept_scores = []

    for box, label, score in zip(boxes, labels, scores):
        label_text = str(label).lower()
        if "window" not in label_text and "door" not in label_text:
            continue

        corners = ip.box_corners(box)
        rays = ip.rays_from_raster_points(selected_node, corners)
        rays_per_object.append([
            {"2d_point": tuple(point), "ray": ray}
            for point, ray in zip(corners, rays)
        ])
        kept_labels.append(label)
        kept_scores.append(float(score))

    rays = {
        Path(selected_node.name).stem: [{
            "rays_per_object": rays_per_object,
            "labels": kept_labels,
            "scores": kept_scores,
        }]
    }
    print(f"Selected image windows/doors: {len(kept_labels)}")
    return rays


def intersect_selected_windows(building, rays):
    intersections = fe.calculate_intersections(building["mesh"], rays)
    intersections_filt = fe.remove_zero_pointsets(intersections)
    intersections_coplanar = fe.filter_coplanar_detections(intersections_filt)

    n_raw = sum(len(entry["intersections"]) for entries in intersections.values() for entry in entries)
    n_filt = sum(len(entry["intersections"]) for entries in intersections_filt.values() for entry in entries)
    n_coplanar = sum(len(entry["intersections"]) for entries in intersections_coplanar.values() for entry in entries)
    print(f"Intersections raw/filter/coplanar: {n_raw} / {n_filt} / {n_coplanar}")
    return intersections, intersections_filt, intersections_coplanar


def quads_from_intersections(intersections):
    quads = []
    for entries in intersections.values():
        for entry in entries:
            for points, label, score in zip(entry["intersections"], entry["labels"], entry["scores"]):
                quads.append({
                    "id": len(quads) + 1,
                    "label": label,
                    "score": score,
                    "points": np.array([point["intersection"] for point in points], dtype=float),
                    "count": 1,
                })
    return quads


def image_lookup(image_nodes):
    lookup = {}
    for node in image_nodes:
        lookup[node.name] = node
        lookup[Path(node.name).stem] = node
    return lookup


def detect_rectified(rectified_dir, model, processor, device):
    detections = {}
    for image_path in sorted(rectified_dir.glob("*.jpg")):
        image = Image.open(image_path).convert("RGB")
        boxes, labels, scores = dp.detect_boxes_labels(
            image,
            model,
            processor,
            device,
            config["detection_text"],
            config["box_threshold"],
            config["text_threshold"],
        )
        detections[image_path.stem] = [{
            "boxes": boxes,
            "labels": labels,
            "scores": scores,
        }]
    print(f"Rectified images detected: {len(detections)}")
    return detections


def rectified_boxes_to_original(transformed_bboxes, filtered_boxes):
    for key, boxes in filtered_boxes.items():
        if key in transformed_bboxes:
            transformed_bboxes[key]["bounding_boxes"] = boxes
    return fe.map_rectified_bboxes_to_original(transformed_bboxes)


def ordered_quad(points):
    points = np.asarray(points, dtype=float)
    top = points[np.argsort(points[:, 1])[:2]]
    bottom = points[np.argsort(points[:, 1])[2:]]
    top = top[np.argsort(top[:, 0])]
    bottom = bottom[np.argsort(bottom[:, 0])]
    return np.array([top[0], top[1], bottom[0], bottom[1]])


def detections_to_image_node_rays(nodes_by_name, detections):
    rays = {}
    for image_id, entries in detections.items():
        node = nodes_by_name.get(image_id)
        if node is None:
            continue

        node_entries = []
        for entry in entries:
            rays_per_object = []
            for corners in entry["corners"]:
                corners = ordered_quad(corners)
                object_rays = ip.rays_from_raster_points(node, corners)
                rays_per_object.append([
                    {"2d_point": tuple(point), "ray": ray}
                    for point, ray in zip(corners, object_rays)
                ])
            node_entries.append({
                "rays_per_object": rays_per_object,
                "labels": entry["labels"],
                "scores": entry["scores"],
            })
        rays[image_id] = node_entries
    return rays


def groups_from_intersections(intersections):
    grouped = fe.group_similar_windows(intersections, threshold=config["grouping_threshold"])
    print(f"Grouped windows/doors: {len(grouped)}")
    mean = fe.mean_and_std_iteratief_filtered(grouped, drempel=2.5, include_single_detections=True)
    print(f"Mean windows/doors: {len(mean)}")
    filtered = fe.filter_raamgroepen_by_angle(mean, tolerance_deg=3)
    print(f"Angle-filtered windows/doors: {len(filtered)}")
    return filtered or mean


def points_labels_from_groups(groups):
    building_translation = np.asarray(config["building_translation"], dtype=float)
    ring_order = [0, 1, 3, 2]
    return {
        "3d_points": [
            (np.asarray(group["gemiddelde_hoekpunten"], dtype=float)[ring_order] - building_translation).tolist()
            for group in groups
        ],
        "labels": [group["label"] for group in groups],
    }


def clear_jpgs(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for image_path in folder.glob("*.jpg"):
        image_path.unlink()


def show_window_quads(building, quads):
    print(f"Window quads to show: {len(quads)}")
    if SHOW_WINDOWS_DOORS:
        meshes = fe.quads_to_meshes(quads)
        lines = fe.quads_to_linesets(quads, color=[1, 1, 0])
        o3d.visualization.draw_geometries([building["mesh"], *meshes, *lines])


def _vertices_world(city_json):
    scale = np.asarray(city_json.get("transform", {}).get("scale", [1, 1, 1]), dtype=float)
    translate = np.asarray(city_json.get("transform", {}).get("translate", [0, 0, 0]), dtype=float)
    return np.asarray(city_json["vertices"], dtype=float) * scale + translate


def _lod3_window_faces(city_json):
    vertices = _vertices_world(city_json)
    faces = []
    for city_object in city_json.get("CityObjects", {}).values():
        for geometry in city_object.get("geometry", []):
            if str(geometry.get("lod")) != "3":
                continue
            surfaces = geometry.get("semantics", {}).get("surfaces", [])
            values = geometry.get("semantics", {}).get("values", [])
            for index, boundary in enumerate(geometry.get("boundaries", [])):
                if index >= len(values):
                    continue
                semantic = surfaces[values[index]]
                if semantic.get("type") not in ("Window", "Door"):
                    continue
                faces.append(vertices[np.asarray(boundary[0], dtype=int)])
    return faces


def write_obj(mesh, city_json, output_path):
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    window_faces = _lod3_window_faces(city_json)
    material_path = output_path.with_suffix(".mtl")

    lines = [
        "# Created by lod3_modeler",
        "# Generated from CityJSON LOD3 MultiSurface",
        f"mtllib {material_path.name}",
        f"# vertices {len(vertices)}",
        f"# faces {len(triangles) + len(window_faces)}",
    ]
    lines += [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in vertices]
    for face in window_faces:
        lines += [f"v {x:.5f} {y:.5f} {z:.5f}" for x, y, z in face]

    lines.append("usemtl Building")
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in triangles]
    lines.append("usemtl Window")
    base = len(vertices)
    for face in window_faces:
        count = len(face)
        lines.append("f " + " ".join(str(base + i + 1) for i in range(count)))
        base += count

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    material_path.write_text(
        "\n".join([
            "newmtl Building",
            "Kd 0.70 0.70 0.70",
            "",
            "newmtl Window",
            "Kd 0.00 0.20 1.00",
            "",
        ]),
        encoding="utf-8",
    )


def write_lod3(city_json, image_nodes, groups):
    city_json = fe.merge_coplanar_adjacent_faces(copy.deepcopy(city_json))
    vertices_labels = fe.transform_to_vertices(points_labels_from_groups(groups), city_json)
    aligned = fe.normal_allignment_to_faces(city_json, vertices_labels, offset_distance=0)
    aligned = fe.filter_overlapping_planes(aligned)
    print(f"Aligned windows/doors after overlap filter: {len(aligned['vertices'])}")

    lod3 = fe.add_cutouts_to_cityjson(city_json, aligned)
    lod3 = fe.duplicate_lod22_geometry(lod3)
    lod3 = fe.add_windows_doors(lod3, aligned, inset_distance=config["window_door_inset"])

    p("lod3_patersonhall_json").parent.mkdir(parents=True, exist_ok=True)
    with p("lod3_patersonhall_json").open("w", encoding="utf-8") as f:
        json.dump(lod3, f, indent=2)
    with p("lod3_windows_doors").open("w", encoding="utf-8") as f:
        json.dump(lod3, f, indent=2)

    lod3_building = bp.parse_cityjson(lod3, lod="3")
    write_obj(lod3_building["mesh"], lod3, p("lod3_patersonhall_obj"))
    print(p("lod3_patersonhall_json"))
    print(p("lod3_patersonhall_obj"))


def main():
    city_json, building = load_building()
    image_nodes, selected_node = load_image_nodes()
    image_geometries = gmu.join_geometries([node.convexHull for node in image_nodes])
    print(f"Image hull geometry vertices: {len(image_geometries.vertices)}")

    model, processor, device = dp.load_detection_model(config["model_id"])
    print(f"Device: {device}")

    image = load_selected_image(selected_node)
    boxes, labels, scores = detect_selected_image(image, model, processor, device)
    debug_selected_rays(building, selected_node, boxes)

    rays1 = selected_window_door_rays(selected_node, boxes, labels, scores)
    intersections1, intersections_filt, intersections_coplanar = intersect_selected_windows(building, rays1)
    quads = quads_from_intersections(intersections_coplanar)
    show_window_quads(building, quads)

    rectified_dir = PROJECT_ROOT / "data" / "output" / "carleton" / "patersonhall_rectified"
    cropped_dir = PROJECT_ROOT / "data" / "output" / "carleton" / "patersonhall_cropped"
    clear_jpgs(rectified_dir)
    clear_jpgs(cropped_dir)
    transformed = fe.homographies_imageProcess(p("image_dir"), intersections_coplanar, rectified_dir, cropped_dir=cropped_dir)
    detections2 = detect_rectified(rectified_dir, model, processor, device)
    detections2 = fe.filter_bounding_boxes(transformed, detections2, offset=20)
    detections2 = rectified_boxes_to_original(transformed, detections2)
    detections2 = fe.convert_annotations(detections2)
    rays2 = detections_to_image_node_rays(image_lookup(image_nodes), detections2)
    intersections2 = fe.calculate_intersections(building["mesh"], rays2)
    intersections2 = fe.remove_zero_pointsets(intersections2)
    intersections2 = fe.filter_coplanar_detections(intersections2)
    groups = groups_from_intersections(intersections2)

    if WRITE_CITYJSON:
        write_lod3(city_json, image_nodes, groups)


if __name__ == "__main__":
    main()
