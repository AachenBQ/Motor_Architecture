#ifndef SIMPLEFOC_TASKING_COMPAT_HPP
#define SIMPLEFOC_TASKING_COMPAT_HPP

/*
 * TASKING VX 1.1r8 accepts C++14 but tokenizes the binary literals used by
 * SimpleFOC v2.4.0 as user-defined integer literals. These reserved literal
 * operators preserve the intended bitmap values without modifying the pinned
 * third-party submodule.
 */
#if defined(__TASKING__)
constexpr unsigned long long operator "" b1000000(unsigned long long)
{
    return 0x40ULL;
}

constexpr unsigned long long operator "" b0100000(unsigned long long)
{
    return 0x20ULL;
}

constexpr unsigned long long operator "" b0010000(unsigned long long)
{
    return 0x10ULL;
}

constexpr unsigned long long operator "" b0001000(unsigned long long)
{
    return 0x08ULL;
}

constexpr unsigned long long operator "" b0000100(unsigned long long)
{
    return 0x04ULL;
}

constexpr unsigned long long operator "" b0000010(unsigned long long)
{
    return 0x02ULL;
}

constexpr unsigned long long operator "" b0000001(unsigned long long)
{
    return 0x01ULL;
}
#endif

#endif
