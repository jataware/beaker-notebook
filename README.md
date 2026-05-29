# Beaker: the AI-first coding notebook

Beaker is a next-generation coding notebook built for the AI era. Beaker seamlessly integrates a Jupyter-like experience with an AI agent that can generate and run code on your behalf. The agent has access to the entire notebook environment as its context, allowing it to make smart decisions about the code it generates and runs. It can even read tracebacks and fix its own errors, and install missing libraries automatically when it needs them.

Beaker also lets you swap effortlessly between a notebook-style coding interface and a chat-style interface, giving you the best of both worlds. Since everything is interoperable with Jupyter, you can always export your notebook and use it in any other Jupyter-compatible environment.

Beaker is built on top of [Archytas](https://github.com/jataware/archytas), our framework for building AI agents that can interact with code. Advanced users can build their own custom agents with custom ReAct toolsets to support any number of use cases.

We like to think of Beaker as a (much better!) drop-in replacement for workflows where you'd normally rely on Jupyter notebooks, and we hope you'll give it a try and let us know what you think.

## Getting Started

Getting Beaker up and running is easy. Install Beaker with:

```bash
pip install beaker-notebook
```

Next, run `beaker config update` to set up your configuration. This creates a `beaker.conf` configuration file (you can find its location at any time with `beaker config find`). You can leave most fields at their defaults, but you'll need to set `LLM_SERVICE_TOKEN` to your OpenAI API key — or the API key for whichever LLM provider you've selected.

Once installed and configured, start a notebook with:

```bash
beaker notebook
``` 

Your notebook server will start up and Beaker will be ready to use at [`localhost:8888`](http://localhost:8888).

## Quick demo

Here is a quick demo of using Beaker to interact with a [free weather API](https://open-meteo.com/en/docs), fetch some data, perform some data transformations and a bit of analysis. This is really just scratching the surface of what you can do with Beaker, but it gives you a sense of the kinds of things it can do.

<div align="center">
  <a href="https://www.youtube.com/watch?v=AP9LT_cxjzY" target="_blank">
    <img src="docs/assets/beaker-movie-3x-optimized-higherres.gif" alt="Beaker demo" width="90%">
  </a>
  <br/>
  Watch original video on <a href="https://www.youtube.com/watch?v=AP9LT_cxjzY">Youtube here</a>.
</div>

## Want to know more?

There is a lot more to Beaker than what we've covered here. The full [documentation](https://jataware.github.io/beaker-notebook/) covers how to customize and extend Beaker — building your own custom contexts, agents, subkernels, and integrations to make Beaker fit your specific needs. It also covers using the `beaker-ts` TypeScript library to embed Beaker into your own front-end application.
