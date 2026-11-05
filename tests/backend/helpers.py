from models.schemas import (
    BBox,
    DocFormat,
    DocType,
    Document,
    Field,
    ProcessingStatus,
    Table,
    TableCell,
    TextSource,
)


def box(y=100):
    return BBox(x0=100, y0=y, x1=300, y1=y + 20)


def make_doc(doc_type, fields, tables=None, doc_id=None, source=TextSource.text_layer, confidence=0.99):
    doc = Document(case_id="c1", filename=f"{doc_type.value}.pdf", sha256="x", format=DocFormat.digital_pdf,
                   doc_type=doc_type, status=ProcessingStatus.ok, tables=tables or [])
    if doc_id:
        doc.id = doc_id
    y = 100
    for name, value in fields.items():
        doc.fields.append(Field(doc_id=doc.id, name=name, value_raw=value, confidence=confidence, page=0,
                                bbox=box(y), source=source))
        y += 40
    return doc


def txn_table(rows, conf=0.99):
    table = Table(doc_id="d", name="transactions", page=0, headers=["date", "description", "debit", "credit", "balance"])
    y = 500
    for row in rows:
        table.rows.append([TableCell(text=c, confidence=conf, bbox=BBox(x0=100 + 100 * i, y0=y, x1=190 + 100 * i, y1=y + 20))
                           for i, c in enumerate(row)])
        y += 30
    return table


DT = DocType
