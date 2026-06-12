#!/usr/bin/env python3
"""OCR downloaded XJU pdfbox page images with RapidOCR."""

from __future__ import annotations

import argparse
import json
import math
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any


_OCR = None


def get_ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
    return _OCR


def box_angle_degrees(box: list[list[float]]) -> float:
    left, right = box[0], box[1]
    return math.degrees(math.atan2(right[1] - left[1], right[0] - left[0]))


def box_position(box: list[list[float]]) -> tuple[float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return sum(ys) / len(ys), sum(xs) / len(xs)


def recognize_page(args: tuple[str, float, float]) -> dict[str, Any]:
    image_path, min_confidence, max_abs_angle = args
    result, elapsed = get_ocr()(image_path)
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []

    for item in result or []:
        box, text, confidence = item
        angle = box_angle_degrees(box)
        row = {
            "box": box,
            "text": text,
            "confidence": float(confidence),
            "angle": angle,
        }
        if confidence < min_confidence or abs(angle) > max_abs_angle:
            dropped.append(row)
        else:
            kept.append(row)

    kept.sort(key=lambda row: box_position(row["box"]))
    page_text = "\n".join(row["text"] for row in kept)

    return {
        "image": image_path,
        "page": Path(image_path).stem,
        "text": page_text,
        "kept_count": len(kept),
        "dropped_count": len(dropped),
        "elapsed": elapsed,
        "raw": {"kept": kept, "dropped": dropped},
    }


def write_document_outputs(
    document_dir: Path,
    output_root: Path,
    workers: int,
    min_confidence: float,
    max_abs_angle: float,
) -> dict[str, Any]:
    fid = document_dir.name
    output_dir = output_root / fid
    pages_dir = output_dir / "pages"
    raw_dir = output_dir / "raw"
    pages_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(document_dir.glob("page_*.jpg"))
    tasks = [(str(image), min_confidence, max_abs_angle) for image in images]
    results: list[dict[str, Any]] = []

    if workers == 1:
        for task in tasks:
            results.append(recognize_page(task))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(recognize_page, task): task[0] for task in tasks}
            for future in as_completed(futures):
                results.append(future.result())

    results.sort(key=lambda item: item["page"])

    combined_parts: list[str] = []
    for result in results:
        page_name = result["page"]
        (pages_dir / f"{page_name}.txt").write_text(result["text"] + "\n", encoding="utf-8")
        (raw_dir / f"{page_name}.json").write_text(
            json.dumps(result["raw"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        combined_parts.append(f"===== {page_name} =====\n{result['text']}".rstrip())

    combined_text = "\n\n".join(combined_parts) + "\n"
    (output_dir / "combined.txt").write_text(combined_text, encoding="utf-8")

    summary = {
        "fid": fid,
        "source_dir": str(document_dir),
        "output_dir": str(output_dir),
        "page_count": len(images),
        "recognized_pages": len(results),
        "min_confidence": min_confidence,
        "max_abs_angle": max_abs_angle,
        "workers": workers,
        "pages": [
            {
                "page": result["page"],
                "kept_count": result["kept_count"],
                "dropped_count": result["dropped_count"],
            }
            for result in results
        ],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("downloads/xju/pdfbox"),
        help="Directory containing per-fid image folders.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("downloads/xju/ocr"),
        help="Directory where OCR text outputs will be written.",
    )
    parser.add_argument("--workers", type=int, default=max(1, min(4, os.cpu_count() or 1)))
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument(
        "--max-abs-angle",
        type=float,
        default=12.0,
        help="Drop OCR lines tilted more than this many degrees; useful for diagonal watermarks.",
    )
    args = parser.parse_args()

    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    document_dirs = sorted(path for path in input_root.iterdir() if path.is_dir())
    all_summaries = []
    for document_dir in document_dirs:
        print(f"OCR {document_dir.name} ...", flush=True)
        summary = write_document_outputs(
            document_dir=document_dir,
            output_root=output_root,
            workers=args.workers,
            min_confidence=args.min_confidence,
            max_abs_angle=args.max_abs_angle,
        )
        print(
            f"done {summary['fid']}: {summary['recognized_pages']}/{summary['page_count']} pages",
            flush=True,
        )
        all_summaries.append(summary)

    (output_root / "summary.json").write_text(
        json.dumps(all_summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
