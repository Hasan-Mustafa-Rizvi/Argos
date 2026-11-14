const BETWEEN_NUMBERS = /(\d)\s*[\u2014\u2013]\s*(\d)/g
const BETWEEN_WORDS = /\s*[\u2014\u2013]\s*/g

/**
 * A record's sentence, as drawn. An em dash or en dash between numbers becomes a hyphen.
 * One set between words becomes a comma. Nothing else about the sentence changes.
 */
export function printSentence(text: string): string {
  return text.replace(BETWEEN_NUMBERS, "$1-$2").replace(BETWEEN_WORDS, ", ")
}
