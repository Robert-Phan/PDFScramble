import pymupdf

doc = pymupdf.open("firsted.pdf") # open a document
page = doc[2]
p0text = page.get_text()

print(page.number)

with open("bobo.txt", "w", encoding="utf-8") as f:
    if isinstance(p0text, str):
        f.write(p0text)
