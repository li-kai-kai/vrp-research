# XJU Downloads

Downloaded page images from the Xinjiang University WebVPN reader.

## Structure

- `pdfbox/<fid>/page_001.jpg ...`:正文页图片，按页码顺序命名。
- `pdfbox/<fid>/manifest.json`:浏览器资源导出清单，保留原始 `pdfboxServlet` URL。
- `ocr/<fid>/combined.txt`:OCR 识别后的整篇文本。
- `ocr/<fid>/pages/`:OCR 识别后的逐页文本。

## Documents

| fid | pages | folder |
| --- | ---: | --- |
| `da8a7b90f1fd20552895c28fece72a94` | 82 | `pdfbox/da8a7b90f1fd20552895c28fece72a94/` |
| `a703fdac28f6e57594fbffc818ecc2d3` | 89 | `pdfbox/a703fdac28f6e57594fbffc818ecc2d3/` |
| `4537a14de99655551f5c5ef6d430e6a2` | 101 | `pdfbox/4537a14de99655551f5c5ef6d430e6a2/` |
| `9fe0af9e79da6c0b6545e6e4c6a1d8ee` | 76 | `pdfbox/9fe0af9e79da6c0b6545e6e4c6a1d8ee/` |

OCR text has been generated for all four documents under `ocr/<fid>/`.

## Regenerate OCR

From the project root:

```bash
uv run python scripts/tools/ocr_xju_downloads.py
```

`pdfbox/` and `ocr/` are local downloaded/generated assets and are ignored by Git.
