include_guard(GLOBAL)

get_filename_component(_LYNXLIB_RUNTIME_PACKAGE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(LYNXLIB_ICU_DATA "${_LYNXLIB_RUNTIME_PACKAGE_ROOT}/res/icudtl.dat")

function(lynxlib_copy_runtime_assets target)
  if(NOT TARGET "${target}")
    message(FATAL_ERROR "lynxlib_copy_runtime_assets target does not exist: ${target}")
  endif()
  if(NOT EXISTS "${LYNXLIB_ICU_DATA}")
    message(FATAL_ERROR "Lynx ICU data file was not found: ${LYNXLIB_ICU_DATA}")
  endif()

  add_custom_command(TARGET "${target}" POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
            "${LYNXLIB_ICU_DATA}"
            "$<TARGET_FILE_DIR:${target}>/icudtl.dat"
    COMMENT "Copying Lynx runtime assets")
endfunction()
