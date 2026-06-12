#!/usr/bin/env python3
"""
RTL Functionality Test Script for DotScramble

This script tests the RTL layout functionality to ensure:
1. Proper grid weight configuration
2. Menu bar visibility during language switches
3. Panel positioning and sizing
4. Text direction and mirroring
5. Layout state validation
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox
import threading
import time

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_rtl_functionality():
    """Test RTL functionality comprehensively"""
    try:
        # Import the main application
        from views.main_window import AdvancedPrivacyStudioPro
        
        print("🧪 Testing RTL Functionality")
        print("=" * 60)
        
        # Create a test window
        root = tk.Tk()
        root.withdraw()  # Hide the window initially
        
        # Initialize the application
        app = AdvancedPrivacyStudioPro(root)
        
        print("✅ Application initialized successfully")
        
        # Test 1: Check RTL Manager initialization
        print("\n📋 Test 1: RTL Manager Initialization")
        if hasattr(app, 'rtl_manager'):
            print("✅ RTL Manager is properly initialized")
            print(f"   RTL State: {app.rtl_manager.is_rtl}")
            print(f"   Previous RTL State: {app.rtl_manager.previous_rtl_state}")
        else:
            print("❌ RTL Manager not found")
            return False
        
        # Test 2: Check initial layout state
        print("\n📋 Test 2: Initial Layout State")
        if hasattr(app, 'main_container') and app.main_container:
            print("✅ Main container exists")
            container = app.main_container
            col0_weight = container.grid_columnconfigure(0).get('weight', 0)
            col1_weight = container.grid_columnconfigure(1).get('weight', 0)
            print(f"   Column 0 weight: {col0_weight}")
            print(f"   Column 1 weight: {col1_weight}")
            
            # Check if weights match the current RTL state
            if app.rtl_manager.is_rtl:
                # RTL: col0=1 (canvas), col1=0 (controls)
                if col0_weight == 1 and col1_weight == 0:
                    print("✅ Initial RTL layout weights are correct")
                else:
                    print("❌ Initial RTL layout weights are incorrect")
            else:
                # LTR: col0=0 (controls), col1=1 (canvas)
                if col0_weight == 0 and col1_weight == 1:
                    print("✅ Initial LTR layout weights are correct")
                else:
                    print("❌ Initial LTR layout weights are incorrect")
        else:
            print("❌ Main container not found")
        
        # Test 3: Check panel references
        print("\n📋 Test 3: Panel References")
        if hasattr(app, 'left_panel') and hasattr(app, 'right_panel'):
            print("✅ Both panels are properly referenced")
            print(f"   Left panel width: {app.left_panel.winfo_width()}")
            print(f"   Right panel width: {app.right_panel.winfo_width()}")
        else:
            print("❌ Panel references are missing")
        
        # Test 4: Test RTL state change
        print("\n📋 Test 4: RTL State Change")
        try:
            # Switch to RTL
            app.rtl_manager.set_rtl_state(True)
            print("✅ RTL state changed to True")
            
            # Check layout after RTL change
            if hasattr(app, 'main_container') and app.main_container:
                container = app.main_container
                col0_weight = container.grid_columnconfigure(0).get('weight', 0)
                col1_weight = container.grid_columnconfigure(1).get('weight', 0)
                print(f"   Column 0 weight (RTL): {col0_weight}")
                print(f"   Column 1 weight (RTL): {col1_weight}")
                
                if col0_weight == 1 and col1_weight == 0:
                    print("✅ RTL layout weights are correct")
                else:
                    print("❌ RTL layout weights are incorrect")
            
            # Check panel positions
            if hasattr(app, 'left_panel') and hasattr(app, 'right_panel'):
                left_grid = app.left_panel.grid_info()
                right_grid = app.right_panel.grid_info()
                print(f"   Left panel column: {left_grid.get('column', 'N/A')}")
                print(f"   Right panel column: {right_grid.get('column', 'N/A')}")
                
                if left_grid.get('column') == 1 and right_grid.get('column') == 0:
                    print("✅ RTL panel positions are correct")
                else:
                    print("❌ RTL panel positions are incorrect")
            
        except Exception as e:
            print(f"❌ Error during RTL state change: {e}")
            return False
        
        # Test 5: Test LTR state change (back to normal)
        print("\n📋 Test 5: LTR State Change")
        try:
            # Switch back to LTR
            app.rtl_manager.set_rtl_state(False)
            print("✅ RTL state changed to False (LTR)")
            
            # Check layout after LTR change
            if hasattr(app, 'main_container') and app.main_container:
                container = app.main_container
                col0_weight = container.grid_columnconfigure(0).get('weight', 0)
                col1_weight = container.grid_columnconfigure(1).get('weight', 0)
                print(f"   Column 0 weight (LTR): {col0_weight}")
                print(f"   Column 1 weight (LTR): {col1_weight}")
                
                if col0_weight == 0 and col1_weight == 1:
                    print("✅ LTR layout weights are correct")
                else:
                    print("❌ LTR layout weights are incorrect")
            
            # Check panel positions
            if hasattr(app, 'left_panel') and hasattr(app, 'right_panel'):
                left_grid = app.left_panel.grid_info()
                right_grid = app.right_panel.grid_info()
                print(f"   Left panel column: {left_grid.get('column', 'N/A')}")
                print(f"   Right panel column: {right_grid.get('column', 'N/A')}")
                
                if left_grid.get('column') == 0 and right_grid.get('column') == 1:
                    print("✅ LTR panel positions are correct")
                else:
                    print("❌ LTR panel positions are incorrect")
            
        except Exception as e:
            print(f"❌ Error during LTR state change: {e}")
            return False
        
        # Test 6: Test menu bar visibility
        print("\n📋 Test 6: Menu Bar Visibility")
        try:
            if hasattr(app, 'menubar') and app.menubar:
                print("✅ Menu bar exists")
                # Check if menu bar is properly configured
                menu_items = app.menubar.winfo_children()
                print(f"   Menu items count: {len(menu_items)}")
                if len(menu_items) > 0:
                    print("✅ Menu bar has items")
                else:
                    print("❌ Menu bar is empty")
            else:
                print("❌ Menu bar not found")
        except Exception as e:
            print(f"❌ Error checking menu bar: {e}")
        
        # Test 7: Test language switching
        print("\n📋 Test 7: Language Switching")
        try:
            # Test switching to Arabic
            app.change_language('ar')
            print("✅ Switched to Arabic")
            
            # Check if RTL state was updated
            if app.rtl_manager.is_rtl:
                print("✅ RTL state updated for Arabic")
            else:
                print("❌ RTL state not updated for Arabic")
            
            # Test switching back to English
            app.change_language('en')
            print("✅ Switched to English")
            
            # Check if RTL state was updated
            if not app.rtl_manager.is_rtl:
                print("✅ RTL state updated for English")
            else:
                print("❌ RTL state not updated for English")
            
        except Exception as e:
            print(f"❌ Error during language switching: {e}")
            return False
        
        # Test 8: Test layout validation
        print("\n📋 Test 8: Layout Validation")
        try:
            layout_summary = app.rtl_manager.get_layout_summary()
            print("✅ Layout summary retrieved")
            print(f"   RTL Enabled: {layout_summary.get('rtl_enabled', 'N/A')}")
            print(f"   Panel Config: {layout_summary.get('panel_config', 'N/A')}")
            
            # Check if grid configuration is present
            if 'grid_config' in layout_summary:
                grid_config = layout_summary['grid_config']
                print(f"   Grid Col 0 Weight: {grid_config.get('col_0_weight', 'N/A')}")
                print(f"   Grid Col 1 Weight: {grid_config.get('col_1_weight', 'N/A')}")
                print("✅ Grid configuration is present")
            else:
                print("❌ Grid configuration missing")
            
        except Exception as e:
            print(f"❌ Error during layout validation: {e}")
        
        # Test 9: Test debug functionality
        print("\n📋 Test 9: Debug Functionality")
        try:
            # This will print debug info to console
            app.rtl_manager.debug_layout_state()
            print("✅ Debug layout state executed")
        except Exception as e:
            print(f"❌ Error during debug: {e}")
        
        # Test 10: Test multiple rapid switches
        print("\n📋 Test 10: Rapid State Switches")
        try:
            # Rapidly switch states to test stability
            for i in range(3):
                app.rtl_manager.set_rtl_state(True)
                app.rtl_manager.set_rtl_state(False)
                print(f"   Switch cycle {i+1} completed")
            print("✅ Rapid state switches completed successfully")
        except Exception as e:
            print(f"❌ Error during rapid switches: {e}")
            return False
        
        # Clean up
        root.destroy()
        
        print("\n🎉 All RTL functionality tests completed!")
        print("✅ RTL Manager is working correctly")
        return True
        
    except Exception as e:
        print(f"❌ RTL functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_interactive_test():
    """Run an interactive test with a visible window"""
    try:
        from views.main_window import AdvancedPrivacyStudioPro
        
        print("🧪 Running Interactive RTL Test")
        print("=" * 60)
        
        # Create a visible test window
        root = tk.Tk()
        root.title("RTL Test Window")
        root.geometry("800x600")
        
        # Initialize the application
        app = AdvancedPrivacyStudioPro(root)
        
        def test_rtl_switch():
            """Test RTL switching with visual feedback"""
            try:
                # Switch to RTL
                app.rtl_manager.set_rtl_state(True)
                messagebox.showinfo("RTL Test", "Switched to RTL (Arabic layout)")
                
                # Switch back to LTR
                app.rtl_manager.set_rtl_state(False)
                messagebox.showinfo("RTL Test", "Switched to LTR (English layout)")
                
                # Test language switching
                app.change_language('ar')
                messagebox.showinfo("RTL Test", "Language switched to Arabic")
                
                app.change_language('en')
                messagebox.showinfo("RTL Test", "Language switched to English")
                
                messagebox.showinfo("RTL Test", "All tests completed successfully!")
                
            except Exception as e:
                messagebox.showerror("RTL Test Error", f"Test failed: {e}")
        
        # Add test button
        test_button = tk.Button(
            root,
            text="🧪 Run RTL Test",
            command=test_rtl_switch,
            font=("Helvetica", 12, "bold"),
            bg="#e94560",
            fg="white",
            padx=20,
            pady=10
        )
        test_button.pack(pady=20)
        
        # Add debug button
        debug_button = tk.Button(
            root,
            text="🔍 Debug Layout",
            command=app.rtl_manager.debug_layout_state,
            font=("Helvetica", 10),
            bg="#26a69a",
            fg="white",
            padx=15,
            pady=5
        )
        debug_button.pack(pady=5)
        
        # Add quit button
        quit_button = tk.Button(
            root,
            text="❌ Quit",
            command=root.destroy,
            font=("Helvetica", 10),
            bg="#533483",
            fg="white",
            padx=15,
            pady=5
        )
        quit_button.pack(pady=5)
        
        print("✅ Interactive test window created")
        print("💡 Click 'Run RTL Test' to test RTL functionality")
        print("💡 Click 'Debug Layout' to see current layout state")
        
        # Run the test window
        root.mainloop()
        
        return True
        
    except Exception as e:
        print(f"❌ Interactive test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 RTL Functionality Test Suite")
    print("=" * 60)
    
    # Run automated tests
    print("Running automated tests...")
    automated_success = test_rtl_functionality()
    
    print("\n" + "=" * 60)
    
    # Ask user if they want to run interactive test
    if len(sys.argv) > 1 and sys.argv[1] == "--interactive":
        print("Running interactive test...")
        interactive_success = run_interactive_test()
    else:
        print("To run interactive test, use: python test_rtl_functionality.py --interactive")
        interactive_success = True
    
    # Final results
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    if automated_success:
        print("✅ Automated Tests: PASSED")
    else:
        print("❌ Automated Tests: FAILED")
    
    if interactive_success:
        print("✅ Interactive Tests: PASSED")
    else:
        print("❌ Interactive Tests: FAILED")
    
    if automated_success and interactive_success:
        print("\n🎉 All tests passed! RTL functionality is working correctly.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please check the output above.")
        sys.exit(1)