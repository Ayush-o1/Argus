/** Joins conditional class names, skipping falsy values. Single shared
 * implementation of the `[a, b && c].filter(Boolean).join(" ")` pattern that
 * was previously copy-pasted across most interactive components. */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
