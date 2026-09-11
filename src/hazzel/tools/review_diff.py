from ..git_review import review


def review_diff(staged=False, path="."):
    try:
        return review(bool(staged), path or ".")
    except Exception as error:
        return f"Tool error: review failed ({error})."
