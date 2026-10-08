from pathlib import Path
import base64
from docx import Document
from docx.shared import Inches, Pt
from app.formatting import DEFAULT_PROFILE, apply_profile, metrics

def test_formats_safe_body_and_preserves_content(tmp_path):
    source=tmp_path/'input.docx'; out=tmp_path/'output.docx'; doc=Document()
    doc.add_heading('Chapter one', 1); p=doc.add_paragraph('This is the report body text.')
    p.runs[0].font.name='Arial'; p.runs[0].font.size=Pt(9)
    listed=doc.add_paragraph('This list content should be formatted.', style='List Paragraph')
    listed.runs[0].font.name='Arial'; listed.runs[0].font.size=Pt(9)
    doc.add_table(rows=1, cols=1).cell(0,0).text='A table stays here'
    sec=doc.sections[0]; sec.orientation=1; sec.page_width,sec.page_height=Inches(11.7), Inches(8.3)
    doc.save(source); before=metrics(source)
    report=apply_profile(source,out,DEFAULT_PROFILE)
    result=Document(out); body=result.paragraphs[1]
    assert body.runs[0].font.name == 'Times New Roman'
    assert round(body.runs[0].font.size.pt) == 12
    assert result.paragraphs[2].runs[0].font.name == 'Times New Roman'
    assert metrics(out)==before and report['changed']['body']==1 and report['changed']['lists']==1
    assert result.tables[0].cell(0,0).text=='A table stays here'

def test_resizes_inline_images_without_removing_them(tmp_path):
    source=tmp_path/'input.docx'; out=tmp_path/'output.docx'; image=tmp_path/'pixel.png'
    image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL8xQAAAABJRU5ErkJggg=='))
    doc=Document(); doc.add_paragraph('Body text'); doc.add_picture(str(image), width=Inches(8)); doc.save(source)
    profile={**DEFAULT_PROFILE, 'extras': {'imageMaxWidth': 3}}
    report=apply_profile(source,out,profile); result=Document(out)
    assert report['changed']['images']==1 and result.inline_shapes[0].width <= Inches(3)
    assert metrics(source)['images']==metrics(out)['images']==1
