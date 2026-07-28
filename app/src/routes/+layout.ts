// v1 needs no backend: the galaxy, the calibration table and the inventory are static
// assets, and all analysis and synthesis happen in the browser (docs/06-architecture.md).
export const prerender = true;
export const ssr = false;
