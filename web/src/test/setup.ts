import "@testing-library/jest-dom/vitest"
import { cleanup, configure } from "@testing-library/react"
import { afterEach } from "vitest"

// Pages load lazily; the first render of a page in a test file waits for its module.
configure({ asyncUtilTimeout: 8000 })

/*
 * jsdom has no media queries, no canvas and no WebGL. Media queries answer "no" unless a test
 * turns reduced motion on, and canvases have no context.
 */
let reduceMotion = false

export function setReducedMotion(on: boolean) {
  reduceMotion = on
}

Object.defineProperty(window, "matchMedia", {
  configurable: true,
  writable: true,
  value: (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reduceMotion : false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  }),
})

HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext
Element.prototype.scrollIntoView = function scrollIntoView() {}

afterEach(() => {
  cleanup()
  window.sessionStorage.clear()
  reduceMotion = false
})
