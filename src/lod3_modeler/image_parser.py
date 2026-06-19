"""Parse camera CSV rows into GEOMAPI ImageNodes."""

import csv
from pathlib import Path

import numpy as np
import open3d as o3d
from geomapi.nodes import ImageNode
from geomapi.utils import geometryutils as gmu


def world_points_from_raster_points(node, raster_points, depth):
    points = np.asarray(raster_points, dtype=float).reshape(-1, 2)
    fx, fy = node.intrinsicMatrix[0, 0], node.intrinsicMatrix[1, 1]
    cx, cy = node.imageWidth / 2, node.imageHeight / 2
    camera_points = np.column_stack(((points[:, 0] - cx) / fx, (points[:, 1] - cy) / fy, np.ones(len(points)))) * depth
    return (node.cartesianTransform @ np.c_[camera_points, np.ones(len(points))].T).T[:, :3]


def raster_points_from_world_points(node, world_points):
    points = np.asarray(world_points, dtype=float).reshape(-1, 3)
    fx, fy = node.intrinsicMatrix[0, 0], node.intrinsicMatrix[1, 1]
    cx, cy = node.imageWidth / 2, node.imageHeight / 2
    camera_points = (np.linalg.inv(node.cartesianTransform) @ np.c_[points, np.ones(len(points))].T).T[:, :3]
    return np.column_stack((
        fx * camera_points[:, 0] / camera_points[:, 2] + cx,
        fy * camera_points[:, 1] / camera_points[:, 2] + cy,
    ))


def rays_from_raster_points(node, raster_points):
    world_points = world_points_from_raster_points(node, raster_points, 1.0)
    origins = np.tile(node.cartesianTransform[:3, 3], (len(world_points), 1))
    directions = gmu.normalize_vectors(world_points - origins)
    return np.hstack((origins, directions))


def box_corners(box):
    x1, y1, x2, y2 = np.asarray(box, dtype=float)
    return np.array([[x1, y1], [x2, y1], [x1, y2], [x2, y2]])


def image_nodes_from_cams_csv(
    cams_csv_path,
    image_folder=None,
    depth=None,
    focal_length_scale=1.0,
    transpose_rotation=False,
    transform_translation=None,
):
    image_nodes = []

    with Path(cams_csv_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            image_path = Path(image_folder) / row["#name"] if image_folder else Path(row["imagePath"])
            rotation = np.array([[float(row[f"R{i}{j}"]) for j in range(3)] for i in range(3)])
            if transpose_rotation:
                rotation = rotation.T
            image_width = int(float(row["width"]))
            image_height = int(float(row["height"]))
            fx = float(row["fx"])
            fy = float(row["fy"])
            cx = float(row["cx"])
            cy = float(row["cy"])
            transform = gmu.get_cartesian_transform(
                rotation=rotation,
                translation=np.array([float(row["x"]), float(row["y"]), float(row["z"])]),
            )

            node = ImageNode(
                cartesianTransform=transform,
                getMetaData=False,
                imageWidth=image_width,
                imageHeight=image_height,
                focalLength35mm=float(row["fx"]) * focal_length_scale,
                principalPointU=cx - image_width / 2,
                principalPointV=cy - image_height / 2,
                intrinsicMatrix=np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]]),
                depth=depth,
            )
            node.path = str(image_path)
            node.name = row["#name"]

            if transform_translation is not None:
                node.transform(translation=np.asarray(transform_translation, dtype=float))

            corners = np.array([[0, 0], [image_width, 0], [0, image_height], [image_width, image_height]])
            vertices = np.vstack(
                (
                    node.cartesianTransform[:3, 3],
                    world_points_from_raster_points(node, corners, node.depth),
                )
            )
            hull = o3d.geometry.TriangleMesh()
            hull.vertices = o3d.utility.Vector3dVector(vertices)
            hull.triangles = o3d.utility.Vector3iVector([[0, 1, 2], [0, 2, 4], [0, 4, 3], [0, 3, 1], [1, 2, 4], [1, 4, 3]])
            hull.compute_vertex_normals()
            node.convexHull = hull
            node.orientedBoundingBox = gmu.get_oriented_bounding_box(node.convexHull)

            image_nodes.append(node)

    return image_nodes
