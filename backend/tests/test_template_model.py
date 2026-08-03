from app.models.template import Template

def test_template_defaults():
    t = Template(
        name="Test",
        category="notice",
        visibility="private",
        uploaded_by=1,
        original_file_path="templates/original/abc.docx",
    )
    assert t.status == "uploaded"
    assert t.version == 1
    assert t.is_locked is False
    assert isinstance(t.original_file_path, str)
    assert b"" not in [t.original_file_path]  # ensure it's not bytes
