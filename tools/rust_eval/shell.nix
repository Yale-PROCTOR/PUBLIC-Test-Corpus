# © 2026 Massachusetts Institute of Technology
# MIT License

let
  pkgs = import <nixpkgs> {};
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    python313
    python313Packages.xmltodict
  ];

  shellHook = ''
    echo "Entered python shell"
  '';
}