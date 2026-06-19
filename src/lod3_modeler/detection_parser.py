"""Small helpers for object detection setup."""


def load_detection_model(model_id):
    import torch
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    processor = AutoProcessor.from_pretrained(model_id)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(device)
    return model, processor, device


def detect_boxes(image, model, processor, device, text, box_threshold, text_threshold):
    import torch

    inputs = processor(images=image, text=text, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[image.size[::-1]],
    )[0]
    return results["boxes"].detach().cpu().numpy()


def detect_boxes_labels(image, model, processor, device, text, box_threshold, text_threshold):
    import torch

    inputs = processor(images=image, text=text, return_tensors="pt").to(device)
    with torch.no_grad():
        outputs = model(**inputs)

    results = processor.post_process_grounded_object_detection(
        outputs,
        inputs.input_ids,
        threshold=box_threshold,
        text_threshold=text_threshold,
        target_sizes=[image.size[::-1]],
    )[0]
    return (
        results["boxes"].detach().cpu().numpy(),
        results["labels"],
        results["scores"].detach().cpu().numpy(),
    )
