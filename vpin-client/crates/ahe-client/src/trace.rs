use serde_json::{json, Value};

pub fn make_trace_step(
    id: &str,
    category: &str,
    title: &str,
    summary: &str,
    detail: Value,
) -> Value {
    json!({
        "id": id,
        "category": category,
        "title": title,
        "summary": summary,
        "detail": detail,
    })
}

pub fn phase_meta(phase_id: &str) -> (&'static str, &'static str) {
    match phase_id {
        "initial" => ("\u{8f93}\u{5165}", "\u{5b9a}\u{70b9}\u{52a0}\u{5bc6}"),
        "after_conv" => ("Conv", "\u{89e3}\u{5bc6} ReLU"),
        "after_pool" => ("MaxPool", "\u{89e3}\u{5bc6} \u{622a}\u{65ad}"),
        "after_fc1" => ("FC1", "\u{89e3}\u{5bc6} ReLU \u{622a}\u{65ad}"),
        "after_fc2" => ("FC2", "\u{89e3}\u{5bc6} logits"),
        _ => ("phase", "\u{2014}"),
    }
}

pub fn emit_progress(cb: &Option<ProgressCb>, event: Value) {
    if let Some(f) = cb {
        f(event);
    }
}

pub type ProgressCb = std::sync::Arc<dyn Fn(Value) + Send + Sync>;
