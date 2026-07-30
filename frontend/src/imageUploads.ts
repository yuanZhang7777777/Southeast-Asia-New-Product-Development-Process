export function imageFiles(files: FileList | File[] | null | undefined): File[] {
  return Array.from(files || []).filter((file) => file.type.startsWith("image/"));
}

export function createKeyedSaveQueue() {
  const pending = new Map<string, Promise<void>>();

  return <T>(key: string, save: () => Promise<T>): Promise<T> => {
    const previous = pending.get(key) || Promise.resolve();
    const current = previous.catch(() => undefined).then(save);
    const settled = current.then(() => undefined, () => undefined);
    pending.set(key, settled);
    void settled.finally(() => {
      if (pending.get(key) === settled) pending.delete(key);
    });
    return current;
  };
}
