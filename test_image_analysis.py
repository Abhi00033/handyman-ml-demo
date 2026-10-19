
from pathlib import Path
from PIL import Image
from transformers import pipeline
import torch
import time

MODEL_NAME = "openai/clip-vit-base-patch32"

CANDIDATE_LABELS = [
    "a photo of a leaking water pipe or plumbing joint",
    "a photo of a leaking faucet or sink",
    "a photo of an electrical panel or circuit breaker",
    "a photo of electrical wiring or an electrical outlet",
    "a photo of a television mounted on a wall",
    "a photo of furniture assembly or carpentry",
    "a photo of a damaged wall or ceiling",
    "a photo of a painting or wall repainting job",
    "a photo of an air conditioner or HVAC equipment",
    "a photo of a household appliance needing repair",
    "a photo of a bathroom or kitchen renovation",
    "a photo of a general home repair",
    "a photo unrelated to home repair"
]


def main():
    print("Device: CPU")
    print("Loading CLIP model. First run requires an internet connection...")

    start = time.time()

    classifier = pipeline(
        task="zero-shot-image-classification",
        model=MODEL_NAME,
        device=-1
    )

    print(f"Model loaded in {time.time() - start:.1f} seconds.")

    image_path = input(
        "\nEnter the full path of a test image: "
    ).strip().strip('"')

    path = Path(image_path)

    if not path.is_file():
        print("ERROR: Image file not found.")
        return

    try:
        with Image.open(path) as original:
            image = original.convert("RGB")

        print("\nAnalyzing image...")
        start = time.time()

        predictions = classifier(
            image,
            candidate_labels=CANDIDATE_LABELS
        )

        print(f"Analysis completed in {time.time() - start:.1f} seconds.")
        print("\nSuggested image categories:")

        for result in predictions[:5]:
            print(
                f"- {result['label']}: "
                f"{result['score']:.1%}"
            )

        print(
            "\nNote: Scores are relative to the candidate labels. "
            "They are not calibrated probabilities that a repair "
            "or diagnosis is correct."
        )

    except Exception as exc:
        print(f"\nImage analysis failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
