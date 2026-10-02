/**
 * Types derived from the generated OpenAPI schema (`api.generated.ts`).
 *
 * `api.ts` uses these so the backend's declared contract, not a hand copy of
 * it, decides what a request may carry and what a response holds:
 *
 * - `ClientPath<M>` is every route the backend serves for method `M`, written
 *   the way `api.ts` passes it to axios (`/projects/${string}` for
 *   `/api/projects/{project_id}`). A call to a route the backend removed or
 *   renamed stops compiling. A template's `${string}` also matches a `/`, so
 *   a wrong suffix after a parameter can still pass; the prefix cannot.
 * - `BodyOf` / `QueryOf` are a route's declared JSON body and query string.
 * - `ResponseOf` is the JSON a route declares for its success status (200, or
 *   202 for the routes that accept work). Every route declares one; a route
 *   that streams instead (the topic summary) has no JSON body and gives `never`.
 */
import type { components, paths } from './api.generated';

export type Schemas = components['schemas'];
export type ApiRoute = keyof paths;
export type Method = 'get' | 'post' | 'put' | 'delete';

type Operation<P extends ApiRoute, M extends Method> = NonNullable<paths[P][M]>;

/**
 * A response model as it arrives. The schema marks a field optional when it
 * has a default, which is right for a request body; on the way out a field
 * with a non-null default is always sent, so it is required here.
 *
 * A nullable field stays optional. That is how the backend declares a key a
 * route sometimes leaves out (`X | None = None`), and those routes send only
 * the keys the handler returned (`response_model_exclude_unset`), so such a
 * field may be absent as well as `null`.
 */
export type Present<T> = T extends readonly (infer U)[]
  ? Present<U>[]
  : T extends object
    ? { [K in keyof T as null extends T[K] ? never : K]-?: Present<T[K]> } & {
        [K in keyof T as null extends T[K] ? K : never]?: Present<T[K]>;
      }
    : T;

/** A named response model as the backend sends it. */
export type Model<N extends keyof Schemas> = Present<Schemas[N]>;

type JsonBody<R> = R extends { content: { 'application/json': infer B } } ? B : never;

/** The JSON body the backend declares for success (200, else 202) from `M P`. */
export type ResponseOf<P extends ApiRoute, M extends Method> =
  Operation<P, M> extends { responses: infer Responses }
    ? Present<
        Responses extends { 200: infer R } ? JsonBody<R> : Responses extends { 202: infer R } ? JsonBody<R> : never
      >
    : never;

/** The JSON request body the backend declares for `M P`. */
export type BodyOf<P extends ApiRoute, M extends Method> =
  Operation<P, M> extends { requestBody?: { content: { 'application/json': infer B } } } ? B : never;

/** The query parameters the backend declares for `M P`. */
export type QueryOf<P extends ApiRoute, M extends Method> =
  Operation<P, M> extends { parameters: { query?: infer Q } } ? NonNullable<Q> : never;

/** `/projects/{project_id}/activity` → `/projects/${string}/activity`. */
type Templated<S extends string> = S extends `${infer Head}{${string}}${infer Tail}`
  ? `${Head}${string}${Templated<Tail>}`
  : S;

/** Every route served for `M`, relative to the axios base URL (`/api`). */
export type ClientPath<M extends Method> = {
  [P in ApiRoute]: paths[P][M] extends undefined
    ? never
    : P extends `/api${infer Rest}`
      ? Templated<Rest>
      : never;
}[ApiRoute];
