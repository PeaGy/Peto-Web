# Fonts for Peto PDF exports

Documents (features/documents, `create_document`) draw their PDF with Tinos 1.340 (Regular, Bold, Italic, Bold
Italic) and code with Cousine 1.241 Regular. They are metric-compatible with Times New Roman and Courier New, which the
DOCX names, so line breaks and page numbers in the PDF preview match Word closely. TrueType builds from
https://github.com/google/fonts/tree/main/ofl/tinos and https://github.com/google/fonts/tree/main/ofl/cousine
(upstream https://github.com/googlefonts/tinos and https://github.com/googlefonts/cousine). License: SIL Open Font
License 1.1, notices in `Tinos-LICENSE.txt` and `Cousine-LICENSE.txt`.

Noto Sans and Noto Serif (Regular, Bold, Italic, Bold Italic) drew the document PDFs before the styles of 2026-10-06
and are no longer used by any code. Source: https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSans and
https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSerif. License notice in `OFL.txt`.

Slides (features/documents/slides) measure text and draw the PDF preview with Liberation Sans (Regular, Bold,
Italic, Bold Italic) and Liberation Serif (Regular, Bold) 2.1.5. They are metric-compatible with Arial and Times
New Roman, which the PPTX names, so line breaks match PowerPoint. Source:
https://github.com/liberationfonts/liberation-fonts (release 2.1.5). License: SIL Open Font License 1.1, notice in
`Liberation-LICENSE.txt`.

Formulas in documents (features/documents/math/layout.py) are drawn with STIX Two Math Regular 2.12, a TrueType build
from https://github.com/google/fonts/tree/main/ofl/stixtwomath (upstream https://github.com/stipub/stixfonts). License:
SIL Open Font License 1.1, notice in `STIX-LICENSE.txt`. Symbols Tinos lacks in ordinary text (≤, ∈, →) are drawn with
it too.

Files are unmodified upstream TrueType fonts. No font download occurs while exporting a document.
