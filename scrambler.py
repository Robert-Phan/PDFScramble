import pymupdf
import re
import json
from dataclasses import dataclass
import time
from typing import Literal
try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    from PIL import Image
    import io
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

@dataclass
class Page:
    index: int
    failed: bool
    chapter: int | Literal['S']
    chapter_page: int

    def __str__(self):
        if self.failed:
            return f"{self.index + 1}: No page number parsed"
        return f"{self.index + 1}: {self.chapter}-{self.chapter_page}"

class Scrambler:
    def __init__(self, fname: str):
        self.doc = pymupdf.open(fname)
        self.init_pages: list[Page] = []
        self.sorted_pages: list[Page] = []
    
    def make_new_pdf(self, output_path: str = "rearranged.pdf", logging: bool = False, manual_json: str | None = None):
        initial = time.time()

        print('_create_initial_page_list')
        self._create_initial_page_list()
        print(time.time() - initial)
        initial = time.time()

        print('_ocr_failed_pages')
        self._ocr_failed_pages(logging=logging)
        print(time.time() - initial)
        initial = time.time()

        if manual_json:
            print('_manual_page_adjustments')
            self._manual_page_adjustments(manual_json)
            print(time.time() - initial)
            initial = time.time()

        print('_rearrange_page_list')
        self._rearrange_page_list()
        print(time.time() - initial)
        initial = time.time()

        print('_create_rearranged_pdf')
        self._create_rearranged_pdf(output_path)
        print(time.time() - initial)
    
    def _create_initial_page_list(self):
        page_num_pattern = re.compile(r"(\d+|S|\$)\W*\-\W*(\d+)\W*")

        for page in self.doc:
            i = int(page.number) #type:ignore
            text = page.get_text()
            
            if not isinstance(text, str):
                continue
                
            res = page_num_pattern.findall(text)

            if len(res) == 0:
                page_el = Page(i, True, 0, 0)
                self.init_pages.append(page_el)
                continue
            
            numbs = res[-1]
            first = numbs[0]
            chapter = "S" if first == "S" or first == "$" else int(first)
            chapter_page = int(numbs[1])

            page_el = Page(i, False, chapter, chapter_page)
            self.init_pages.append(page_el)

    def _ocr_failed_pages(self, logging: bool = False) -> None:
        """Second pass: use OCR on pages where initial text extraction failed.
        
        Only processes pages with is_none=True. OCRs the bottom 1/5th of each
        page to save processing time, then applies the same regex pattern.
        
        Args:
            logging: If True, write OCR details to ocr_log.txt including:
                     - Page index
                     - Raw OCR text
                     - Whether regex matched
                     - Last regex match if available
        """
        if not HAS_OCR:
            print("Warning: pytesseract and PIL not available. Skipping OCR pass.")
            return
        
        page_num_pattern = re.compile(r"(\d+|S)\W*\-\W*(\d+)\W*")
        log_lines = []
        
        for idx, page_el in enumerate(self.init_pages):
            if not page_el.failed:
                continue  # Only process failed pages
            
            page = self.doc[page_el.index]
            rect = page.rect
            
            # Define bottom 1/5th of the page
            bottom_fifth = pymupdf.Rect(
                rect.x0, 
                rect.y1 - rect.height / 5, 
                rect.x1, 
                rect.y1
            )
            
            # Get pixmap of bottom portion
            pix = page.get_pixmap(clip=bottom_fifth)
            
            # Convert to PIL Image and run OCR
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data)) #type: ignore
            text = pytesseract.image_to_string(img) #type: ignore
            
            # Apply same regex pattern
            res = page_num_pattern.findall(text)
            
            # Log information if logging enabled
            if logging:
                log_lines.append(f"Page Index: {page_el.index}")
                log_lines.append(f"Raw OCR Text: {repr(text)}")
                log_lines.append(f"Regex Matched: {len(res) > 0}")
                if len(res) > 0:
                    log_lines.append(f"Last Match: {res[-1]}")
                log_lines.append("")
            
            if len(res) > 0:
                numbs = res[-1]
                first = numbs[0]
                chapter = "S" if first == "S" else int(first)
                chapter_page = int(numbs[1])
                
                # Replace the failed page with successful parse
                self.init_pages[idx] = Page(page_el.index, False, chapter, chapter_page)
        
        # Write log file if logging enabled
        if logging and log_lines:
            with open("ocr_log.txt", 'w', encoding="utf-8") as f:
                f.write('\n'.join(log_lines))

    def _manual_page_adjustments(self, json_path: str) -> None:
        """Adjust remaining failed pages using manual JSON corrections.
        
        The JSON file should contain one object where:
        - Keys are page indices (offset by +1, so key "2" = index 1)
        - Values are [chapter, chapter_page] tuples
        
        Args:
            json_path: Path to the JSON file containing manual page adjustments
        """
        with open(json_path, 'r', encoding="utf-8") as f:
            adjustments = json.load(f)
        
        for key, value in adjustments.items():
            # Key is offset by +1, so subtract 1 to get actual index
            page_index = int(key) - 1
            chapter = value[0]  # Can be int or "S"
            chapter_page = value[1]
            
            # Convert chapter to proper type
            if isinstance(chapter, str):
                if chapter == "S":
                    chapter = "S"
                else:
                    chapter = int(chapter)
            else:
                chapter = int(chapter)
            
            # Find and update the page in init_pages
            for idx, page_el in enumerate(self.init_pages):
                if page_el.index == page_index:
                    # Replace with corrected page
                    self.init_pages[idx] = Page(page_index, False, chapter, chapter_page)
                    break

    def _rearrange_page_list(self) -> None:
        def sort_key(p: Page):
            if p.failed:
                return (1, float("inf"), float("inf"), p.index)
            chap_key = p.chapter if isinstance(p.chapter, int) else float("inf")
            return (0, chap_key, p.chapter_page, p.index)

        # Do not sort in place; produce a new sorted list
        self.sorted_pages = sorted(self.init_pages, key=sort_key)

    def _create_rearranged_pdf(self, output_path: str) -> None:
        """Create a new PDF whose pages are ordered by `self.sorted_pages`.

        Each element's `index` refers to the page number in the original
        document (0-based). Pages are copied in that order to the new PDF.
        """
        if not self.sorted_pages:
            raise ValueError("sorted_pages is empty. Run rearrange_page_list() first.")

        new_doc = pymupdf.open()
        for p in self.sorted_pages:
            new_doc.insert_pdf(self.doc, from_page=p.index, to_page=p.index)
        new_doc.save(output_path)
        new_doc.close()

    def log(self, fname="log.txt"):
        with open(fname, 'w', encoding="utf-8") as f:
            for page in self.init_pages:
                f.write(str(page) + '\n')


scrambler = Scrambler('firsted.pdf')
scrambler.make_new_pdf(
    output_path="rearranged2.pdf", 
    manual_json="manual.json"
)
