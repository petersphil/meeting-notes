from meeting_notes.formatting import timestamp, transcript_markdown
from meeting_notes.whisper import TranscriptSegment
def test_timestamp_and_transcript():
    assert timestamp(3661.9) == "01:01:01"
    output = transcript_markdown([TranscriptSegment(0, 2.4, "Hello", "SPEAKER_00")], {"SPEAKER_00": "Phil"})
    assert "[00:00:00–00:00:02] Phil" in output and "Hello" in output
