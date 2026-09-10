"""
Vision AI adapter placeholder.

Production recommendation:
- Send each drawing page as a high-resolution image to a vision-capable model.
- Ask it to return STRICT JSON matching the 15 target columns.
- Include the OCR text as auxiliary evidence.
- Require the model to preserve exact drawing wording for DESCRIPTION.
- Require every uncertain value to be null/blank and add a REVIEW reason.
- Run a second validation pass that checks:
  * item number continuity
  * quantity/UOM consistency
  * line number/drawing number/revision consistency
  * duplicate rows
  * schedule/size compatibility
  * fabrication vs erection section
  * cut-pipe-length table vs pipe quantity

This file intentionally contains no provider-specific credentials or API calls.
"""

TARGET_SCHEMA = {
    "AREA": "string",
    "LINE NO.": "string",
    "DRAWING NO.": "string",
    "REV.": "string",
    "SHEET": "string",
    "ITEM": "string",
    "SIZE (IN)": "string",
    "SCHEDULE/CLASS": "string",
    "MOC": "string",
    "GRADE": "string",
    "DESCRIPTION": "string",
    "QTY": "number",
    "UOM": "string",
    "REMARKS": "string",
}
