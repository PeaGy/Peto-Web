# Fonts for Peto PDF exports

Noto Sans and Noto Serif Regular, Bold, Italic and Bold Italic are bundled so Vietnamese
text renders without relying on fonts installed on the VPS.

Source: https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSans

Essay style: https://github.com/notofonts/noto-fonts/tree/main/hinted/ttf/NotoSerif

Slides (features/documents/slides) measure text and draw the PDF preview with Liberation Sans (Regular, Bold,
Italic, Bold Italic) and Liberation Serif (Regular, Bold) 2.1.5. They are metric-compatible with Arial and Times
New Roman, which the PPTX names, so line breaks match PowerPoint. Source:
https://github.com/liberationfonts/liberation-fonts (release 2.1.5). License: SIL Open Font License 1.1, notice in
`Liberation-LICENSE.txt`.

Files are unmodified upstream TrueType fonts. License: SIL Open Font License
1.1; the full upstream notice is in `OFL.txt`. No font download occurs while
exporting a document.
