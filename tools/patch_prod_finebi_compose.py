from pathlib import Path

path = Path("/opt/hengzhe-new-product/app/docker-compose.yml")
text = path.read_text()
if "      - finebi-cache:/data/finebi\n" not in text:
    text = text.replace(
        "      - plm-cache:/data/plm\n      - source-workbooks:/app/.private_uploads",
        "      - plm-cache:/data/plm\n      - finebi-cache:/data/finebi\n      - source-workbooks:/app/.private_uploads",
    )
if "  finebi-cache:\n" not in text:
    text = text.replace("  plm-cache:\n  source-workbooks:", "  plm-cache:\n  finebi-cache:\n  source-workbooks:")
path.write_text(text)
