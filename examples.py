"""
Invoice Splitter - Usage Examples
"""

from invoice_splitter import InvoiceSplitter
import os


def example_1_basic_usage():
    """Example 1: Basic usage with default settings"""
    splitter = InvoiceSplitter()
    
    # Split a PDF
    output_files = splitter.split_pdf("invoices.pdf")
    
    print(f"Created {len(output_files)} invoice files:")
    for file in output_files:
        print(f"  - {file}")


def example_2_custom_output_directory():
    """Example 2: Specify custom output directory"""
    splitter = InvoiceSplitter()
    
    output_files = splitter.split_pdf(
        "invoices.pdf",
        output_dir="./processed_invoices"
    )
    
    print(f"Saved {len(output_files)} invoices to ./processed_invoices/")


def example_3_explicit_api_key():
    """Example 3: Provide API key explicitly"""
    # Useful when running in different environments
    api_key = "sk-your-api-key"
    
    splitter = InvoiceSplitter(api_key=api_key)
    output_files = splitter.split_pdf("invoices.pdf")
    
    print(f"Processed with explicit API key: {len(output_files)} invoices")


def example_4_batch_processing():
    """Example 4: Process multiple PDF files"""
    splitter = InvoiceSplitter()
    
    pdf_files = ["invoices_2024_q1.pdf", "invoices_2024_q2.pdf"]
    
    for pdf_file in pdf_files:
        try:
            output_files = splitter.split_pdf(pdf_file, f"output_{pdf_file.split('.')[0]}")
            print(f"✓ {pdf_file}: {len(output_files)} invoices")
        except Exception as e:
            print(f"✗ {pdf_file}: {e}")


def example_5_error_handling():
    """Example 5: Proper error handling"""
    try:
        splitter = InvoiceSplitter()
        output_files = splitter.split_pdf("nonexistent.pdf")
    except FileNotFoundError as e:
        print(f"File error: {e}")
    except ValueError as e:
        print(f"Configuration error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


def example_6_integration_with_workflow():
    """Example 6: Integrate into a larger workflow"""
    splitter = InvoiceSplitter()
    
    # Process invoices
    output_files = splitter.split_pdf("all_invoices.pdf", "temp_split")
    
    # Next steps could be:
    # - Send to OCR/extraction service
    # - Upload to accounting system
    # - Archive by vendor
    # - Extract data with another tool
    
    print(f"Step 1: Split {len(output_files)} invoices")
    print("Step 2: (Process further - send to accounting system, etc.)")
    print("Step 3: (Archive and log)")


if __name__ == "__main__":
    print("Invoice Splitter - Usage Examples\n")
    print("=" * 50)
    
    # Uncomment the example you want to run:
    
    # example_1_basic_usage()
    # example_2_custom_output_directory()
    # example_3_explicit_api_key()
    # example_4_batch_processing()
    # example_5_error_handling()
    # example_6_integration_with_workflow()
    
    print("\nTo run an example, uncomment it in the file and run:")
    print("  python examples.py")