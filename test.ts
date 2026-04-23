type MyReturnType<T> = T extends (...args: any[])=>infer R ? R : never
type MyParameters<T> = T extends (...args:infer R)=>any ?R:never

type MyPartial<T> = {[P in keyof T]?:T[P]}

type MyRequire<T> = {[P in keyof T]-?:T[P]}

type MyReadOnly<T> = {readonly[P in keyof T]:T[P]}

type MyPick<T,K extends keyof T> = {[P in K]:T[P]}

type MyExclude<T,U> = T extends U ? never:T

type MyExtract<T,U> = T extends U ? T:never

type MyNotNullable<T> = T extends null | undefined ? never :T

type MyOmit<T, K extends keyof T> = MyPick<T,Exclude<keyof T, K>>

