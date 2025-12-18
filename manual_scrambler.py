import json
import pymupdf

class ManualScrambler:
    """Manually reorder pages of a PDF based on a JSON mapping.

    JSON format: { "<page>": <after_page>, ... }
    - Keys and values are 1-based page numbers.
    - Each key page is moved to be immediately AFTER the value page.
      Example: {"20": 5} moves page 20 to become the new page 6.
    - Multiple moves are applied in ascending order of the target (value).
      Earlier insertions shift later positions, matching the example
      where moving page 20 after 5 makes page 30 moved after 10 end up
      at position 12 (not 11).
    """

    def __init__(self, input_path: str, output_path: str, json_path: str):
        self.input_path = input_path
        self.output_path = output_path
        self.json_path = json_path

    def rearrange(self) -> None:
        doc = pymupdf.open(self.input_path)
        page_count = doc.page_count

        # Load moves from JSON
        with open(self.json_path, 'r', encoding="utf-8") as f:
            raw = json.load(f)

        # Normalize to list of (orig_page, after_page) as ints (1-based)
        moves: list[tuple[int, int]] = []
        for k, v in raw.items():
            orig_page = int(k)
            after_page = int(v)
            if not (1 <= orig_page <= page_count):
                raise ValueError(f"Invalid source page {orig_page}; PDF has {page_count} pages")
            if not (1 <= after_page <= page_count):
                raise ValueError(f"Invalid target page {after_page}; PDF has {page_count} pages")
            if orig_page == after_page:
                # Moving a page after itself is a no-op; skip
                continue
            moves.append((orig_page, after_page))

        # Deterministic order: apply moves by ascending target page
        moves.sort(key=lambda x: (x[1], x[0]))

        # Current order tracked by original page numbers (1-based)
        order: list[int] = list(range(1, page_count + 1))

        for orig_page, after_page in moves:
            # Remove the page to move from its current position
            if orig_page in order:
                cur_idx = order.index(orig_page)
                order.pop(cur_idx)
            else:
                # Already removed by a prior move of the same page; skip
                continue

            # Find current position of the target page (by identity)
            try:
                after_idx = order.index(after_page)
            except ValueError:
                # Target page itself might have been moved already; still referenced by identity
                # If truly missing, treat as appending to end
                after_idx = len(order) - 1

            insert_pos = after_idx + 1
            order.insert(insert_pos, orig_page)

        # Build the new document by copying pages in the computed order
        new_doc = pymupdf.open()
        for pnum in order:
            src_index = pnum - 1  # convert 1-based to 0-based
            new_doc.insert_pdf(doc, from_page=src_index, to_page=src_index)

        new_doc.save(self.output_path)
        new_doc.close()
        doc.close()
