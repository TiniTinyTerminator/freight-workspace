//! Safe Rust wrapper around the `libtexprintf` C library.
//!
//! The default build does not link to the native GPL-3.0 library. Enable the
//! `native` feature and make `libtexprintf` available to the linker to render
//! TeX-like math through `stexprintf`.

use std::borrow::Cow;
use std::error::Error as StdError;
use std::ffi::NulError;
use std::fmt;

/// Render TeX-like math with default options.
pub fn render(input: &str) -> Result<String, Error> {
    RenderOptions::default().render(input)
}

/// Options forwarded to libtexprintf's global render settings.
#[derive(Debug, Clone, Default)]
pub struct RenderOptions {
    line_width: Option<i32>,
    font: Option<Cow<'static, str>>,
}

impl RenderOptions {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn line_width(mut self, line_width: impl Into<Option<i32>>) -> Self {
        self.line_width = line_width.into().filter(|width| *width > 0);
        self
    }

    pub fn font(mut self, font: impl Into<Cow<'static, str>>) -> Self {
        self.font = Some(font.into());
        self
    }

    pub fn render(&self, input: &str) -> Result<String, Error> {
        native_render(self, input)
    }
}

#[derive(Debug)]
pub enum Error {
    NativeDisabled,
    InteriorNul(NulError),
    RenderFailed,
    ParseFailed { output: String },
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NativeDisabled => {
                f.write_str("libtexprintf support was built without the native feature")
            }
            Self::InteriorNul(_) => f.write_str("input contains an interior NUL byte"),
            Self::RenderFailed => f.write_str("libtexprintf returned a null output pointer"),
            Self::ParseFailed { output } => {
                write!(
                    f,
                    "libtexprintf reported a parse error while rendering {output:?}"
                )
            }
        }
    }
}

impl StdError for Error {
    fn source(&self) -> Option<&(dyn StdError + 'static)> {
        match self {
            Self::InteriorNul(err) => Some(err),
            _ => None,
        }
    }
}

impl From<NulError> for Error {
    fn from(err: NulError) -> Self {
        Self::InteriorNul(err)
    }
}

#[cfg(feature = "native")]
fn native_render(options: &RenderOptions, input: &str) -> Result<String, Error> {
    native::render(options, input)
}

#[cfg(not(feature = "native"))]
fn native_render(_options: &RenderOptions, _input: &str) -> Result<String, Error> {
    Err(Error::NativeDisabled)
}

#[cfg(feature = "native")]
mod native {
    use super::{escape_printf_format, Error, RenderOptions};
    use std::ffi::{c_char, c_int, c_void, CStr, CString};
    use std::sync::Mutex;

    static TEXPRINTF_LOCK: Mutex<()> = Mutex::new(());

    extern "C" {
        static mut TEXPRINTF_LW: c_int;
        static mut TEXPRINTF_FONT: *mut c_char;
        static mut TEXPRINTF_ERR: c_int;

        fn stexprintf(format: *const c_char, ...) -> *mut c_char;
        fn free(ptr: *mut c_void);
    }

    pub fn render(options: &RenderOptions, input: &str) -> Result<String, Error> {
        let format = CString::new(escape_printf_format(input))?;
        let font = options
            .font
            .as_ref()
            .map(|font| CString::new(font.as_ref()))
            .transpose()?;
        let _guard = TEXPRINTF_LOCK
            .lock()
            .expect("libtexprintf render lock poisoned");

        unsafe {
            let old_width = TEXPRINTF_LW;
            let old_font = TEXPRINTF_FONT;

            TEXPRINTF_ERR = 0;
            TEXPRINTF_LW = options.line_width.unwrap_or(0);
            if let Some(font) = &font {
                TEXPRINTF_FONT = font.as_ptr() as *mut c_char;
            }

            let ptr = stexprintf(format.as_ptr());

            TEXPRINTF_LW = old_width;
            TEXPRINTF_FONT = old_font;

            if ptr.is_null() {
                return Err(Error::RenderFailed);
            }
            let output = CStr::from_ptr(ptr).to_string_lossy().into_owned();
            free(ptr.cast::<c_void>());

            if TEXPRINTF_ERR != 0 {
                TEXPRINTF_ERR = 0;
                return Err(Error::ParseFailed { output });
            }
            Ok(output)
        }
    }
}

#[cfg(any(feature = "native", test))]
fn escape_printf_format(input: &str) -> String {
    if !input.contains('%') {
        return input.to_owned();
    }

    let mut escaped = String::with_capacity(input.len() + input.matches('%').count());
    for ch in input.chars() {
        escaped.push(ch);
        if ch == '%' {
            escaped.push('%');
        }
    }
    escaped
}

#[cfg(test)]
mod tests {
    use super::escape_printf_format;

    #[cfg(feature = "native")]
    use super::RenderOptions;

    #[test]
    fn escapes_printf_percent_markers() {
        assert_eq!(
            escape_printf_format(r"\text{100% ready}"),
            r"\text{100%% ready}"
        );
    }

    #[test]
    fn leaves_regular_tex_unchanged() {
        assert_eq!(
            escape_printf_format(r"\frac{\alpha}{x+1}"),
            r"\frac{\alpha}{x+1}"
        );
    }

    #[cfg(feature = "native")]
    #[test]
    fn native_render_sample_output() {
        let rendered = RenderOptions::new()
            .line_width(80)
            .render(r"\frac{\alpha}{\beta+x^2}")
            .expect("native libtexprintf render should succeed");
        println!("rendered: {rendered:?}");
        assert!(!rendered.trim().is_empty());
        assert_ne!(rendered, r"\frac{\alpha}{\beta+x^2}");
    }
}
