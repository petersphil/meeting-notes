from meeting_notes.speaker_map import display_speaker, load_speaker_map
def test_json_speaker_map(tmp_path):
    path = tmp_path / "speakers.json"; path.write_text('{"SPEAKER_00": "Phil Peters"}', encoding="utf-8")
    mapping = load_speaker_map(path); assert mapping == {"SPEAKER_00": "Phil Peters"}; assert display_speaker("SPEAKER_00", mapping) == "Phil Peters"
def test_text_speaker_map(tmp_path):
    path = tmp_path / "speakers.txt"; path.write_text("# comment\nSPEAKER_00 = Phil\nSPEAKER_01: Alex\n", encoding="utf-8")
    assert load_speaker_map(path)["SPEAKER_01"] == "Alex"
