const KEY = "docuforensic.reviewer";

export function getReviewer(): string {
  try {
    return localStorage.getItem(KEY) ?? "examiner";
  } catch {
    return "examiner";
  }
}

export function setReviewer(name: string) {
  try {
    localStorage.setItem(KEY, name);
  } catch {
    // Storage can be blocked; the name then lasts for this input only.
  }
}
