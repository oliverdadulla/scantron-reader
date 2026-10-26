import re


def expand_item_nos(item_nos_str: str) -> list:
    result = []
    parts = re.split(r",\s*", str(item_nos_str).strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        range_match = re.fullmatch(r"(\d+)-(\d+)", part)
        single_match = re.fullmatch(r"(\d+)", part)

        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start > end:
                print(f"  ⚠️  Warning: invalid range '{part}' (start > end), skipping.")
                continue
            result.extend(range(start, end + 1))
        elif single_match:
            result.append(int(single_match.group(1)))
        else:
            print(f"  ⚠️  Warning: cannot parse item number part '{part}', skipping.")

    return result
