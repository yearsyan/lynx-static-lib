include_guard(GLOBAL)

get_filename_component(_LYNXLIB_RUNTIME_PACKAGE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(LYNXLIB_ICU_DATA "${_LYNXLIB_RUNTIME_PACKAGE_ROOT}/res/icudtl.dat")
set(LYNXLIB_CORE_JS "${_LYNXLIB_RUNTIME_PACKAGE_ROOT}/res/lynx_core.js")
set(LYNXLIB_CORE_DEV_JS "${_LYNXLIB_RUNTIME_PACKAGE_ROOT}/res/lynx_core_dev.js")

function(lynxlib_copy_icu_data target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "lynxlib_copy_icu_data target does not exist: ${target}")
  endif()
  if(NOT EXISTS "${LYNXLIB_ICU_DATA}")
    message(FATAL_ERROR "Lynx ICU data file was not found: ${LYNXLIB_ICU_DATA}")
  endif()

  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${LYNXLIB_ICU_DATA}"
            "$<TARGET_FILE_DIR:${target}>/icudtl.dat"
    COMMENT "Copying Lynx ICU data")
endfunction()

function(lynxlib_copy_core_js_assets target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "lynxlib_copy_core_js_assets target does not exist: ${target}")
  endif()
  if(NOT EXISTS "${LYNXLIB_CORE_JS}")
    message(FATAL_ERROR "Lynx core JS file was not found: ${LYNXLIB_CORE_JS}")
  endif()
  if(NOT EXISTS "${LYNXLIB_CORE_DEV_JS}")
    message(FATAL_ERROR "Lynx core dev JS file was not found: ${LYNXLIB_CORE_DEV_JS}")
  endif()

  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${LYNXLIB_CORE_JS}"
            "$<TARGET_FILE_DIR:${target}>/lynx_core.js"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${LYNXLIB_CORE_DEV_JS}"
            "$<TARGET_FILE_DIR:${target}>/lynx_core_dev.js"
    COMMENT "Copying Lynx core JS assets")
endfunction()

function(lynxlib_copy_runtime_assets target)
  lynxlib_copy_icu_data("${target}")
  lynxlib_copy_core_js_assets("${target}")
endfunction()
