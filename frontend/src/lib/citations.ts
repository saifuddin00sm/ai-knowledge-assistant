/**
 * Citation plumbing.
 *
 * The API returns answers containing inline `[1]`, `[2]` markers plus a
 * `sources` array those numbers index into. Rather than parse the answer by
 * hand, markers are rewritten as markdown links to `#cite-n`, which lets
 * react-markdown hand them to a custom anchor renderer. Any marker outside the
 * range of returned sources is left as plain text - the API already strips
 * citations that do not map to a source, so this is only belt-and-braces.
 */

export const CITE_HREF_PREFIX = "#cite-";

/** DOM id of a source card, used to scroll to it from a citation chip. */
export function sourceElementId(messageId: string, index: number): string {
  return `source-${messageId}-${index}`;
}

/** `[2]` -> `[2](#cite-2)`, only for markers that have a matching source. */
export function linkifyCitations(answer: string, sourceCount: number): string {
  if (sourceCount <= 0) return answer;
  // Skip markers already followed by "(" so real markdown links survive.
  return answer.replace(/\[(\d+)\](?!\()/g, (match, digits: string) => {
    const index = Number.parseInt(digits, 10);
    const valid = Number.isInteger(index) && index >= 1 && index <= sourceCount;
    return valid ? `[${index}](${CITE_HREF_PREFIX}${index})` : match;
  });
}

/** Returns the citation number for a `#cite-n` href, or null. */
export function citationIndexFromHref(href: string | undefined): number | null {
  if (!href || !href.startsWith(CITE_HREF_PREFIX)) return null;
  const index = Number.parseInt(href.slice(CITE_HREF_PREFIX.length), 10);
  return Number.isInteger(index) ? index : null;
}
