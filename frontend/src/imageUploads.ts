export function imageFiles(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files || []).filter((file) => file.type.startsWith("image/"));
}
