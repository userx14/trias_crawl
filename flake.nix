{
  description = "Mobidata BW crawler";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  outputs = { self, nixpkgs }: 
  let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
    pythonEnv = pkgs.python3.withPackages (ps: with ps; [
      requests
      numpy
      svgpathtools
      xmltodict

    ]);
  in
  {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = [ pythonEnv ];
    };
  };
}
