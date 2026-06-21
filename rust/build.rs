fn main() {
    winres::WindowsResource::new()
        .set_icon("favicon.ico")
        .set_manifest_file("app.manifest")
        .compile()
        .unwrap();
}