from coursera_scraper.cli import classify_target, extract_slug


def test_classify_url_specialization():
    assert classify_target("https://www.coursera.org/specializations/ibm-ai-workflow", False) == (
        "specialization",
        "ibm-ai-workflow",
    )


def test_classify_url_course():
    assert classify_target("https://www.coursera.org/learn/some-course", False) == (
        "course",
        "some-course",
    )


def test_classify_slug_default_course():
    assert classify_target("some-course", False) == ("course", "some-course")


def test_classify_slug_with_flag():
    assert classify_target("some-spec", True) == ("specialization", "some-spec")


def test_classify_url_wins_over_flag():
    # a /learn/ URL stays a course even if --specialization is passed
    assert classify_target("https://www.coursera.org/learn/foo", True) == ("course", "foo")


def test_extract_slug_plain():
    assert extract_slug("foo-bar") == "foo-bar"
