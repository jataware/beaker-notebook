
variable "tag" {
  default = "latest"
  type = string
}

variable "packages" {
  default = {
    beaker-notebook = "./wheel-builder.Dockerfile"
  }
  type = map(string)
}

variable "JULIA_ENABLED" {
  default = true
  type = bool
}

variable "R_ENABLED" {
  default = true
  type = bool
}

group "default" {
  targets = ["notebook", "server"]
}

group "packages" {
  targets = formatlist("package-%s", keys(packages))
}

target "package-builder" {
  name = "package-${package}"
  dockerfile = packages[package]
  contexts = {
    src = "${dirname(packages[package])}/..",
    base = "target:base",
  }
  matrix = {
    package = keys(packages)
  }
  output = ["type=cacheonly"]
}

target "package-collector" {
  dockerfile-inline = join("\n", concat([
      "FROM scratch",
      "WORKDIR /dist",
    ],
    [
      for source in keys(packages):
      "COPY --from=${source} /dist/*.whl /dist/"
    ],
  ))

  contexts = {
    for package in keys(packages):
    package => "target:package-${package}"
  }
  output = ["type=cacheonly"]
}


target "base" {
  dockerfile = "base.Dockerfile"
  contexts = {
    assets = "./assets"
  }
  output = ["type=cacheonly"]
}

target "notebook" {
  dockerfile = "notebook.Dockerfile"
  context = "."
  contexts = {
    base = "target:base",
    packages = "target:package-collector",
  }
  args = {
    JULIA_ENABLED = JULIA_ENABLED
    R_ENABLED = R_ENABLED
  }
  tags = [
    "beaker-notebook:${tag}"
  ]
}

target "server" {
  dockerfile = "server.Dockerfile"
  contexts = {
    beaker-notebook = "target:notebook"
  }
  tags = [
    "beaker-server:${tag}"
  ]
}

target "dev" {
  dockerfile = "dev.Dockerfile"
  contexts = {
    assets = "./assets"
    beaker-notebook = "target:notebook"
  }
  tags = [
    "beaker-dev:${tag}"
  ]
}
