import { definePreset, palette, shade, tint, mix, dt } from '@primevue/themes';
import type { Preset, Theme, PaletteDesignToken } from '@primeuix/themes/types';
import Aura from '@primeuix/themes/aura';
import { makePalette } from './util';

const primarySurfaceColor = '#708da9';

const lightSurfacePalette: PaletteDesignToken = makePalette(primarySurfaceColor, 7, 95);
const lightPrimaryPalette: PaletteDesignToken = makePalette("#7254f3");

const BeakerTheme: Preset = definePreset(Aura, {
    semantic: {
        primary: lightPrimaryPalette,
        colorScheme: {
            light: {
                surface: <PaletteDesignToken>{
                    ...lightSurfacePalette,
                    border: dt('surface.200'),
                    a: dt('surface.0'),
                    b: dt('surface.50'),
                    c: dt('surface.100'),
                    d: dt('surface.200'),
                    e: dt('surface.300'),
                    f: dt('surface.400'),
                    g: dt('surface.500'),
                    h: dt('surface.600'),
                    i: dt('surface.700'),
                    j: dt('surface.800'),
                    k: dt('surface.900'),
                    l: dt('surface.950'),
                }

            },
            // Allow default dark palette generation from light version.
            dark: {
                surface: <PaletteDesignToken>{
                    ...lightSurfacePalette,
                    border: dt('surface.800'),
                    a: dt('surface.950'),
                    b: dt('surface.900'),
                    c: dt('surface.800'),
                    d: dt('surface.700'),
                    e: dt('surface.600'),
                    f: dt('surface.500'),
                    g: dt('surface.400'),
                    h: dt('surface.300'),
                    i: dt('surface.200'),
                    j: dt('surface.100'),
                    k: dt('surface.50'),
                    l: dt('surface.0'),
                },
            }
        },
    },
    components: {
        panel: {
            header: {
                borderRadius: `${dt('panel.root.borderRadius')} ${dt('panel.root.borderRadius')} 0 0`,
            },
            extend: {
                contentBorderRadius: `0 0 ${dt('panel.root.borderRadius')} ${dt('panel.root.borderRadius')}`,
            }
        },
        dialog: {
            extend: {
                "headerImage": "linear-gradient(45deg, var(--p-surface-a), var(--p-surface-a), var(--p-surface-a), var(--p-surface-b), var(--p-surface-b), var(--p-surface-b));",
            }
        },
        toolbar: {
            root: {
                background: 'var(--p-surface-b)',
            }
        },
        menubar: {
            root: {
                background: 'var(--p-surface-b)',
            }
        },
        datatable: {
            headerCell: {
                background: 'var(--p-surface-b)',
            }
        },
    },
    extend: {
        surface: {
            borderRadius: "6px",
        },
        tree: {
            borderColor: `solid 1px ${dt('content.border.color')}`,
        },
    },
    css: ({dt}) => `
:root {
  font-family:Lato, Helvetica, sans-serif;
  --font-family:Lato, Helvetica, sans-serif;
  font-size: 12pt;
  font-weight: 400;
}

/* lato-300 - latin-ext_latin */
@font-face {
  font-family: "Lato";
  font-style: normal;
  font-weight: 300;
  src: local("Lato Light"), local("Lato-Light"), url("/themes/fonts/lato-v17-latin-ext_latin-300.woff2") format("woff2"), url("/themes/fonts/lato-v17-latin-ext_latin-300.woff") format("woff");
  /* Chrome 6+, Firefox 3.6+, IE 9+, Safari 5.1+ */
}
/* lato-regular - latin-ext_latin */
@font-face {
  font-family: "Lato";
  font-style: normal;
  font-weight: 400;
  src: local("Lato Regular"), local("Lato-Regular"), url("/themes/fonts/lato-v17-latin-ext_latin-regular.woff2") format("woff2"), url("/themes/fonts/lato-v17-latin-ext_latin-regular.woff") format("woff");
  /* Chrome 6+, Firefox 3.6+, IE 9+, Safari 5.1+ */
}
/* lato-700 - latin-ext_latin */
@font-face {
  font-family: "Lato";
  font-style: normal;
  font-weight: 700;
  src: local("Lato Bold"), local("Lato-Bold"), url("/themes/fonts/lato-v17-latin-ext_latin-700.woff2") format("woff2"), url("/themes/fonts/lato-v17-latin-ext_latin-700.woff") format("woff");
  /* Chrome 6+, Firefox 3.6+, IE 9+, Safari 5.1+ */
}

@font-face {
  font-family: 'Ubuntu Mono';
  font-style: italic;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ubuntumono/v19/KFOhCneDtsqEr0keqCMhbCc_CsE.ttf) format('truetype');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-style: italic;
  font-weight: 700;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ubuntumono/v19/KFO8CneDtsqEr0keqCMhbCc_Mn33tYg.ttf) format('truetype');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-style: normal;
  font-weight: 400;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ubuntumono/v19/KFOjCneDtsqEr0keqCMhbBc9.ttf) format('truetype');
}
@font-face {
  font-family: 'Ubuntu Mono';
  font-style: normal;
  font-weight: 700;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/ubuntumono/v19/KFO-CneDtsqEr0keqCMhbC-BL-Hy.ttf) format('truetype');
}

.monospace {
  font-family: 'Ubuntu Mono', 'Courier New', Courier, monospace;
}

.pre {
    white-space: pre-wrap;
}

.p-button-icon.beaker-zoom {
    &::after {
        content: "\e908";
        font-size: 50%;
        position: absolute;
        right: 38%;
        top: 45%;
    }
}

:root {
    /* Define missing CSS custom properties for backward compatibility */
    --highlight-text-color: ${dt('primary.color')};
    --text-color: ${dt('text.color')};
    --text-color-secondary: ${dt('text.muted.color')};
}

/* Light mode specific variables */
:root:not(.beaker-dark) {
    --text-color-secondary: #6b7280; /* Gray-500 for better contrast in light mode */
}

/* Dark mode specific variables */
:root.beaker-dark {
    --text-color-secondary: #9ca3af; /* Gray-400 for better contrast in dark mode */
}

.p-panel-content {
    border-radius: ${dt('panel.contentBorderRadius')};
}

.p-dialog-header {
    background-image: ${dt('dialog.headerImage')};
    border-top-left-radius: inherit;
    border-top-right-radius: inherit;
}

.p-dialog-footer {
    border-bottom-left-radius: inherit;
    border-bottom-right-radius: inherit;
}
    `,
});

export default BeakerTheme;
