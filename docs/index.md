---
layout: default
title: Home
nav_order: 1
has_toc: true
---

# Beaker: the AI-first coding notebook

Beaker is a next generation coding notebook built for the AI era. Beaker seamlessly integrates a Jupyter-like experience with an AI agent that can be used to generate and run code on the user's behalf. The agent has access to the entire notebook environment as its context, allowing it to make smart decisions about the code it generates and run. It can even debug itself and fix errors so that you don't have to. When the agent wants to use a library that isn't installed, it can even install it automatically. 

Beaker also lets you swap effortlessly between a notebook style coding interface and a chat style interface, giving you the best of both worlds. Since everything is interoperable with Jupyter, you can always export your notebook and use it in any other Jupyter-compatible environment.

Beaker is powered by [Archytas](https://github.com/jataware/archytas), our framework for building AI agents that can interact with code. Advanced users can generate their own custom agents to meet their specific needs. These agents can have custom ReAct toolsets built in and can be extended to support any number of use cases.

We like to think of Beaker as a (much better!) drop in replacement for workflows where you'd normally rely on Jupyter notebooks and we hope you'll give it a try and let us know what you think!

## Quick demo

Here is a quick demo of using Beaker to interact with a [free weather API](https://open-meteo.com/en/docs), fetch some data, perform some data transformations and a bit of analysis. This is really just scratching the surface of what you can do with Beaker, but it gives you a sense of the kinds of things it can do.

<div align="center">
<iframe class="youtube" width="560" height="315" src="https://www.youtube.com/embed/AP9LT_cxjzY?si=8y-WqQzL0kUGwQIP" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
</div>


## How Beaker works

The Beaker kernel acts as a custom Python kernel that sits between the user
interface and the execution environment (subkernel) and passes messages to and
from the subkernel, performing actions as needed in either the Beaker layer or
the subkernel layer. The Beaker kernel inspects each message that passes
through it and may take extra actions as needed. This allows you to define
custom message types that result in custom behavior, have extra behavior be
triggered by normal actions, or modify the request and/or response messages on
the fly.

When it is first initialized, the Beaker kernel will start a subkernel using
its defaults (usually Python3). If you check the existing kernels in the Jupyter
service, will see both kernels listed. At this point, you can use Beaker as if
it were actual  and all regular messages will be sent to the subkernel as if you
were connected directly to the subkernel itself. To really get started with
Beaker, you need to set a context.


## Contexts

Contexts provide behind-the-scenes magic to make Beaker work for you. 
Contexts let you add extra functionality to Beaker to support your specific use case, including custom data loaders,
bespoke tools for your agent to utilize, customized LLM prompts, and custom actions that facilitate integration with external applications.
Though Beaker's out of the box context provides robust functionality for a wide array of programming and data analysis tasks, 
you can easily create and set custom [contexts](./contexts.html). With a custom context, Beaker now understands the mission 
and has specialized tools at its disposal.


## How is Beaker different from Jupyter?

We like to think of Beaker as Jupyter on AI steroids. It provides much the same functionality as a 
Jupyter notebook except that the user has access to a conversational agent that can 
write and run code. This is hugely beneficial for speeding up data analysis tasks and for tedious things like
generating plotting code. Since the agent has full visibility to the entire notebook environment it can write
high fidelity code that typically works out of the box. When its code fails though, it can automatically read tracebacks
and fix its errors. 

Beaker also lets you swap effortlessly between a notebook style coding interface and a chat style interface, giving you the best of both worlds. 

Since everything is interoperable with Jupyter, you can always export your notebook and use it in any other Jupyter-compatible environment.
