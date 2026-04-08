# Trias crawl
Utility to download live delay data from mobidata bw trias api and visualize delay for s-bahn stuttgart trains.
![demo screenshot](exampleLivemap.png)

## Requirements
The project need python with the libraries requests, svgpathtools and xmltodict.

On nixos it is possible to initialize a temporary development environment with the `nix develop` command.

## Notes on setting up the webserver
- disable caching in apache or nginx, otherwise the svg images will not be refreshed on the client side
