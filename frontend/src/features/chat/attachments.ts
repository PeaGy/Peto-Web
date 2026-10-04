

export const MAX_FILES = 16;
export const MAX_MEDIA_FILES = 4;
export const MAX_FILE_BYTES = 8 * 1024 * 1024;
export const MAX_TOTAL_BYTES = 16 * 1024 * 1024;

export function isImageFile(file: File): boolean {
  return file.type.startsWith("image/") || /\.(png|jpe?g|gif|webp)$/i.test(file.name);
}

/** Bảng tính Excel đọc được: .xlsx và .xlsm (macro không bao giờ chạy). Định dạng .xls cũ máy chủ từ chối. */
export function isSpreadsheetFile(file: File): boolean {
  return /\.xls[xm]$/i.test(file.name) ||
    file.type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    file.type === "application/vnd.ms-excel.sheet.macroEnabled.12";
}

export function isMediaFile(file: File): boolean {
  return (
    isImageFile(file) ||
    isSpreadsheetFile(file) ||
    file.type === "application/pdf" ||
    /\.pdf$/i.test(file.name) ||
    file.type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    /\.docx$/i.test(file.name)
  );
}


export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      const comma = result.indexOf(",");
      resolve(comma >= 0 ? result.slice(comma + 1) : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error("Không đọc được tệp"));
    reader.readAsDataURL(file);
  });
}


