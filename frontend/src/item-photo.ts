// Keep camera uploads below Vercel's 4.5 MB request limit on every photo input.
const MAX_UPLOAD_BYTES = 4 * 1024 * 1024;

export async function resizePhoto(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file, {
    imageOrientation: "from-image",
  });
  const ratio = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
  canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("Cannot prepare photo");
  }
  try {
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  } finally {
    bitmap.close();
  }
  for (const quality of [0.85, 0.7, 0.55]) {
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (result) =>
          result ? resolve(result) : reject(new Error("Cannot prepare photo")),
        "image/jpeg",
        quality,
      ),
    );
    if (blob.size <= MAX_UPLOAD_BYTES) return blob;
  }
  throw new Error("Photo is too large. Choose a smaller photo.");
}
