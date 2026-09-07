from meeting_notes.summarize import parse_actions
def test_parse_actions_json_and_fence():
    actions = parse_actions('```json\n[{"action":"Send notes","owner":"Phil","due":"Friday"}]\n```')
    assert len(actions) == 1 and actions[0].owner == "Phil"
def test_parse_actions_rejects_non_json():
    assert parse_actions("Here are some notes, but no JSON") == []
