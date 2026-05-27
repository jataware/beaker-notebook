---
layout: default
title: Previews
parent: Context Development
grand_parent: Development
nav_order: 4
has_toc: true
---

# Previews

Contexts can optionally return previews to indicate the state inside the
context.

The preview can return multiple representations of the state for any number of
items needing preview.

## Adding a preview to your context

Add a generate_preview() function! You can show data types or specific variables as they are with `display()`, or for more custom visualization logic, add more plotting and figures through whatever library you choose.

Matplotlib example:

```python
    async def generate_preview(self):
        """
        Preview what exists in the subkernel.
        """
        # Change the code here to fit your desired preview logic.
        # Make sure to wrap it in a try/except block! 
        user_plotting_code = r'''
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

try:
    # Show the dataframe itself first to map to 'Raw Data' below
    display(context_var)          
    plt.figure(figsize=(10, 6))
    plt.plot(context_var.mean(), marker='o', linestyle='-', color='blue')
    plt.title('Mean Values Across Columns')
    plt.xlabel('Column Index')
    plt.ylabel('Mean Value')
    plt.grid(True)
    # Show the column means second
    plt.show()
except Exception as e:
    pass
'''
        # Names in order of figures to show the user in Beaker's interface, handled
        # in the logic below.
        plot_names = [
            "Raw Data",
            "Column Mean"
        ]

        #
        # Internal preview handling - collect all figures and map them to names.
        #
        result = await self.evaluate(user_plotting_code)
        plots = result.get('display_data_list', None)
        collected_plots = {
            (plot_names[i:i+1] or [i])[0]: plots[i] 
            for i in range(len(plots))
        }
        if len(plots) > 0:
            return {
                'Preview': collected_plots
            }
```

Vega-Altair example -- plots an interactive bar chart around the variable `source`:

(assuming `source` would later be defined in the notebook in the shape of   
```python
source = {
    "values": [
        {"a": "A", "b": 28},
        {"a": "B", "b": 55},
        {"a": "C", "b": 43},
        {"a": "D", "b": 91},
        {"a": "E", "b": 81},
        {"a": "F", "b": 53},
        {"a": "G", "b": 19},
        {"a": "H", "b": 87},
        {"a": "I", "b": 52},
    ]
}
```  
)

as per https://altair-viz.github.io/gallery/interactive_bar_select_highlight.html

```python
    async def generate_preview(self):
        """
        Preview what exists in the subkernel.
        """
        # Change the code here to fit your desired preview logic.
        # Make sure to wrap it in a try/except block! 
        user_plotting_code = '''
try:
    import altair as alt
    
    select = alt.selection_point(name="select", on="click")
    highlight = alt.selection_point(name="highlight", on="pointerover", empty=False)
    stroke_width = (
        alt.when(select).then(alt.value(2, empty=False))
        .when(highlight).then(alt.value(1))
        .otherwise(alt.value(0))
    )
                                     
    alt.Chart(source, height=200).mark_bar(
        fill="#4C78A8", stroke="black", cursor="pointer"
    ).encode(
        x="a:O",
        y="b:Q",
        fillOpacity=alt.when(select).then(alt.value(1)).otherwise(alt.value(0.3)),
        strokeWidth=stroke_width,
    ).configure_scale(bandPaddingInner=0.2).add_params(select, highlight).show()
except Exception as e:
    pass
'''
        # Names in order of figures to show the user in Beaker's interface, handled
        # in the logic below.
        plot_names = [
            "Interactive Vega Plot"
        ]

        #
        # Internal preview handling - collect all figures and map them to names.
        #
        result = await self.evaluate(user_plotting_code)
        plots = result.get('display_data_list', None)
        collected_plots = {
            (plot_names[i:i+1] or [i])[0]: plots[i] 
            for i in range(len(plots))
        }
        if len(plots) > 0:
            return {
                'Preview': collected_plots
            }
```


For a good starting point, changing anything above the "Internal preview handling" section should be good enough for an arbitrary number of custom plots and dataframes!

## Format of a preview payload

```javascript
{
  <item_type>: {
    <item_name>: {
      <mimetype>: <any json-encodable content>
    }
  }
}
```

**Example:**
```javascript
{
    "datasets": {
        "hospitals": {
            "application/json": [
                [...],
                [...],
                [...]
            ],
            "text/html": "<table><tr>...</table>",
            "text/plain": "hosp_id,hosp_name,hosp_city_id,..."

        },
        "cities": {
            "application/json": [[...],[...],[...]],
            "text/html": "<table><tr>...</table>",
            "text/plain": "id,name,state,..."
        },
        "doctors": {
            "application/json": [[...],[...],[...]],
            "text/html": "<table><tr>...</table>",
            "text/plain": "doctor_id,doctor_name,doctor_hosp_id,..."
        }
    },
    "maps": {
        "arlington_va": {
            "image/jpeg": "/9j/4AAQSkZJRg...RQB//2Q==",
            "text/plain": "Map of Arlington, VA"
        },
        "washington_dc": {
            "image/jpeg": "/9j/4AAQSkFikk...vRn//2Q==",
            "text/plain": "Map of Washington, DC"
        }
    },
    "pins": {
        "pins": {
            "application/x-doctor-location": [
                {
                    "lat": -77.0361691,
                    "lon": 38.9049533,
                    "doctor_id": 4335,
                },
                {
                    "lat": -77.0437808,
                    "lon": 38.9048841,
                    "doctor_id": 8146,
                },
                {
                    "lat": -77.0496311,
                    "lon": 38.9200379,
                    "doctor_id": 2380,
                }
            ]
        }
    }
}
```


### Item types

This is a unique identifier for the type of item being previewed. Either
displayed or used as a selection criteria as needed.

Useful for grouping like items together if more than one type of item is being
previewed.


### Item names

This is a unique name of the item being previewed and should be identifiable by
the user. Usually this will be a variable name for a local variable type.


### MIME Types

A [MIME Type](https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types)
indicator the determines how the preview should be rendered.

You can provide your own mimetype if you also create a renderer for it.

#### The following MIME Types have renderers built in provide by Jupyter:

* text/plain
* text/html
* text/markdown
* image/bmp
* image/png
* image/jpeg
* image/gif
* image/webp
* image/svg+xml
* text/javascript
* application/javascript
* application/vnd.jupyter.stdout  ( Custom Jupyter type )
* application/vnd.jupyter.stderr  ( Custom Jupyter type )

#### These MIME Types have renderers defined in the Beaker-vue library

* text/latex
* application/latex
* text/json
* application/json

<br/>

## Adding a new renderer
