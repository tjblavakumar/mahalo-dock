/**
 * The bundled `@types/react-grid-layout@1.3.5` only declares the default
 * (fixed-width) `ReactGridLayout` component. It omits the `Responsive` and
 * `WidthProvider` exports, plus the `ResponsiveProps` breakpoint props, even
 * though they exist at runtime (see node_modules/react-grid-layout/index.js).
 *
 * This augmentation adds the missing named exports so we can build a
 * responsive, auto-width grid in a type-safe way.
 */
import * as React from "react";
import type { CoreProps, Layout, Layouts } from "react-grid-layout";

declare module "react-grid-layout" {
  interface ResponsiveProps extends CoreProps {
    /** Layouts keyed by breakpoint name (e.g. { lg: [...], md: [...] }). */
    layouts?: Layouts;
    /** Breakpoint name -> min container width in px. */
    breakpoints?: { [breakpoint: string]: number };
    /** Breakpoint name -> number of columns. */
    cols?: { [breakpoint: string]: number };
    /** Margin between items [x, y] (px), optionally per breakpoint. */
    margin?: [number, number] | { [breakpoint: string]: [number, number] };
    /** Padding of the container [x, y] (px), optionally per breakpoint. */
    containerPadding?:
      | [number, number]
      | { [breakpoint: string]: [number, number] };
    rowHeight?: number;
    onLayoutChange?: (currentLayout: Layout[], allLayouts: Layouts) => void;
    onBreakpointChange?: (newBreakpoint: string, newCols: number) => void;
  }

  class Responsive extends React.Component<ResponsiveProps> {}

  interface WidthProviderProps {
    measureBeforeMount?: boolean;
  }

  function WidthProvider<P>(
    component: React.ComponentType<P>
  ): React.ComponentType<P & WidthProviderProps>;
}
