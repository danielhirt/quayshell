{
  description = "Quayshell persistent Wayland terminal";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = function:
        nixpkgs.lib.genAttrs systems (system: function nixpkgs.legacyPackages.${system});
    in {
      packages = forAllSystems (pkgs: {
        default = pkgs.python3Packages.buildPythonApplication {
          pname = "quayshell";
          version = "0.3.0";
          pyproject = true;
          src = self;

          build-system = [ pkgs.python3Packages.setuptools ];
          dependencies = [ pkgs.python3Packages.pygobject3 ];
          nativeBuildInputs = [ pkgs.gobject-introspection pkgs.wrapGAppsHook4 ];
          buildInputs = [ pkgs.gtk4 pkgs.gtk4-layer-shell pkgs.vte-gtk4 ];

          nativeCheckInputs = [ pkgs.python3Packages.pytest pkgs.zsh ];
          checkPhase = "pytest";

          meta = {
            description = "Persistent Wayland terminal";
            homepage = "https://github.com/danielhirt/quayshell";
            license = pkgs.lib.licenses.mit;
            platforms = pkgs.lib.platforms.linux;
            mainProgram = "quayshell";
          };
        };
      });

      apps = forAllSystems (pkgs:
        let system = pkgs.stdenv.hostPlatform.system;
        in {
          default = {
            type = "app";
            program = "${self.packages.${system}.default}/bin/quayshell";
            meta.description = "Persistent Wayland terminal";
          };
        });
    };
}
