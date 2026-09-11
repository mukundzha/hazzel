from ..git_review import review


def review_diff(staged=False, path=".", codebase=False):
    try:
        return review(bool(staged), path or ".", bool(codebase))
    except Exception as error:
        return f"Tool error: review failed ({error})."
