// Guard: the lints required by the guide (§ 3) are declared in the workspace.
#[test]
fn workspace_declares_required_lints() {
    let manifest =
        std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../Cargo.toml")).unwrap();
    let doc: toml::Table = manifest.parse().unwrap();
    let lints = &doc["workspace"]["lints"];
    assert_eq!(lints["rust"]["unsafe_code"].as_str(), Some("forbid"));
    for name in [
        "unwrap_used",
        "expect_used",
        "todo",
        "unimplemented",
        "dbg_macro",
        "allow_attributes_without_reason",
        "wildcard_enum_match_arm",
    ] {
        assert_eq!(
            lints["clippy"][name].as_str(),
            Some("deny"),
            "clippy::{name}"
        );
    }
}
