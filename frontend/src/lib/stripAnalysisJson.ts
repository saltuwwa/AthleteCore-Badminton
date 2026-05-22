/** Remove analyst JSON from visible chat text (backend also strips; safety net). */
export const stripAnalysisJsonFromText = (text: string): string =>
  text
    .replace(/```json[\s\S]*?```/gi, '')
    .replace(/\{[\s\S]*"errors"[\s\S]*\}/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
