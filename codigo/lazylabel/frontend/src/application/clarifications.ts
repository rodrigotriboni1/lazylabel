import { ApiError } from '@/application/ports/LazyLabelClient'

/** Questions the planner returns (HTTP 422) when a request is ambiguous; null for any other error. */
export function clarificationQuestions(cause: unknown): string[] | null {
  return cause instanceof ApiError && cause.status === 422 && typeof cause.body === 'object' && cause.body !== null
    && 'questions' in cause.body && Array.isArray(cause.body.questions) ? cause.body.questions as string[] : null
}
