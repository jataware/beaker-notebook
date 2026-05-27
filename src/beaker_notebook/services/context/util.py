
def is_different(left, right) -> bool:
    """
    Determines if two objects are different or not for use in find_differences()
    """
    if isinstance(left, dict) and isinstance(right, dict):
        left_keys = set(left.keys())
        right_keys = set(right.keys())
        left_keys.discard("last_updated")
        right_keys.discard("last_updated")

        if left_keys != right_keys:
            return True

        for key in left_keys:
            if is_different(left[key], right[key]):
                return True
        # Same keys and values (ignoring last_updated), so they are not different
        return False
    elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return True
        return any(is_different(left_item, right_item) for left_item, right_item in zip(left, right))
    else:
        return left != right


def find_differences(prev: dict, new: dict) -> dict:
    """
    Returns a dictionary that contains the changed values between prev and new.
    Compares recursively, but returns the full new object at the top level.
    Keys contained in prev/new are expected to be the same.

    E.g:
    ```
    prev = {
        "a": 1,
        "b": 2,
        "c": {
            "d": 3
        }
    }
    new = {
        "a": 1,
        "b": 0,
        "c": {
            "e": 3
        }
    }

    find_differeces(prev, new) == {
        "b": 0,
        "c": {
            "e": 3
        }
    }
    """
    result = {}
    for key in new.keys():
        if key == "last_updated":
            continue
        if is_different(prev.get(key, None), new[key]):
            result[key] = new[key]
    return result
