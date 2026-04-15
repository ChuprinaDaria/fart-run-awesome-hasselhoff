//! health — project health scanner for vibe coders.

mod common;
mod file_tree;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;
    Ok(())
}
