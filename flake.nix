{
  description = "Bambu Plotter: guided pen plotting for Bambu Lab printers";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    bun2nix = {
      url = "github:nix-community/bun2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      bun2nix,
    }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs [
        "aarch64-linux"
        "x86_64-linux"
        "aarch64-darwin"
      ];

      # Python deps come from uv.lock, frontend deps from bun.nix (regenerated
      # from bun.lock by the postinstall script).
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};

          pythonSet =
            (pkgs.callPackage pyproject-nix.build.packages { python = pkgs.python314; }).overrideScope
              (
                lib.composeManyExtensions [
                  pyproject-build-systems.overlays.wheel
                  (workspace.mkPyprojectOverlay { sourcePreference = "wheel"; })
                ]
              );
          venv = pythonSet.mkVirtualEnv "bambu-plotter-env" workspace.deps.default;

          frontend = pkgs.stdenv.mkDerivation {
            pname = "bambu-plotter-frontend";
            version = "0.1.0";
            src = lib.fileset.toSource {
              root = ./.;
              fileset = lib.fileset.unions [
                ./package.json
                ./bun.lock
                ./tsconfig.json
                ./vite.config.js
                ./frontend
              ];
            };
            nativeBuildInputs = [ bun2nix.packages.${system}.default.hook ];
            bunDeps = bun2nix.packages.${system}.default.fetchBunDeps { bunNix = ./bun.nix; };
            # The only lifecycle script is our own postinstall (bun2nix).
            dontRunLifecycleScripts = true;
            buildPhase = ''
              runHook preBuild
              bun run build
              runHook postBuild
            '';
            installPhase = ''
              runHook preInstall
              cp -r static/build $out
              runHook postInstall
            '';
          };
        in
        {
          default = pkgs.stdenv.mkDerivation {
            pname = "bambu-plotter";
            version = "0.1.0";
            src = lib.fileset.toSource {
              root = ./.;
              fileset = lib.fileset.unions [
                ./app
                ./templates
              ];
            };
            nativeBuildInputs = [ pkgs.makeWrapper ];
            # The app finds templates/ and static/ relative to where it runs.
            installPhase = ''
              share=$out/share/bambu-plotter
              mkdir -p $share/static $out/bin
              cp -r app templates $share/
              # Copied, not linked: StaticFiles won't follow a symlink out.
              cp -r ${frontend} $share/static/build
              makeWrapper ${venv}/bin/fastapi $out/bin/bambu-plotter \
                --chdir $share \
                --set-default INERTIA_DEV 0 \
                --add-flags "run app/main.py"
            '';
            meta.mainProgram = "bambu-plotter";
          };
        }
      );

      nixosModules.default = import ./nix/module.nix self;
    };
}
